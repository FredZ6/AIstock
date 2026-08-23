from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine
from stock_platform.application.ingestion.jobs import IngestionJobSpec
from stock_platform.application.ingestion.raw_writer import RawWriter
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.ingestion.models import DataPurpose, FeedType, IngestionRequest
from stock_platform.infrastructure.db.models.tables import (
    ingestion_raw_link,
    normalization_dispatch,
    normalized_record,
    raw_data_object,
)
from stock_platform.infrastructure.ingestion.job_store import IngestionJobStore
from stock_platform.infrastructure.providers.base import ProviderRecord
from stock_platform.infrastructure.providers.persistence import PostgresProviderRecordStore
from stock_platform.workers.ingestion_tasks import (
    dispatch_pending_normalization,
    normalize_dispatched_record,
)

NOW = datetime(2026, 8, 23, 14, tzinfo=UTC)
BODY = b'{"event_time":"2026-08-23T13:59:00Z","close":"182.10"}'


def _alembic_config(database_url: str) -> Config:
    config = Config(str(Path(__file__).parents[3] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _record(
    *, payload: dict[str, object] | None = None, object_key: str | None = None
) -> ProviderRecord:
    content_hash = hashlib.sha256(BODY).hexdigest()
    return ProviderRecord(
        symbol=Symbol("NVDA"),
        feed_type=FeedType.PRICE_BARS,
        provider="ALPACA",
        event_time=NOW - timedelta(minutes=1),
        available_at=NOW,
        ingested_at=NOW,
        content_hash=content_hash,
        raw_object_key=object_key or f"live/ALPACA/price_bars/{content_hash}.json",
        payload=payload or {"close": "182.10"},
    )


class RecordingRawStore:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.keys: list[str] = []

    def put(self, object_key: str, content: bytes, content_type: str) -> None:
        self.keys.append(object_key)
        assert content == BODY
        assert content_type == "application/json"
        if self.fail:
            raise OSError("object store unavailable")


def _job_id(engine: Engine) -> UUID:
    store = IngestionJobStore(engine)
    return store.enqueue(
        IngestionJobSpec(
            request=IngestionRequest(
                {"provider": "ALPACA", "dataset": "price_bars", "symbol": "NVDA"}
            ),
            provider="ALPACA",
            dataset=FeedType.PRICE_BARS,
            window_start=NOW - timedelta(minutes=1),
            window_end=NOW,
            purpose=DataPurpose.RESEARCH,
            policy_version="ingestion-v1",
            max_attempts=3,
        ),
        now=NOW,
    )


def test_provider_persistence_is_idempotent_but_rejects_immutable_conflicts(
    isolated_database_url: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    record = _record()
    with engine.begin() as connection:
        store = PostgresProviderRecordStore(connection)
        store.persist(record, "alpaca-price-bars-v1")
        store.persist(record, "alpaca-price-bars-v1")
        with pytest.raises(ValueError, match="immutable normalized record conflict"):
            store.persist(
                _record(payload={"close": "999.99"}),
                "alpaca-price-bars-v1",
            )
        with pytest.raises(ValueError, match="immutable raw object conflict"):
            store.persist(
                _record(object_key="live/ALPACA/price_bars/conflict.json"),
                "alpaca-price-bars-v1",
            )

        assert (
            connection.execute(select(func.count()).select_from(raw_data_object)).scalar_one() == 1
        )
        assert (
            connection.execute(select(func.count()).select_from(normalized_record)).scalar_one()
            == 1
        )
    engine.dispose()


def test_raw_writer_requires_object_storage_before_database_commit(
    isolated_database_url: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    job_id = _job_id(engine)
    writer = RawWriter(engine=engine, raw_store=RecordingRawStore(fail=True))

    with pytest.raises(OSError, match="object store unavailable"):
        writer.write(
            job_id=job_id,
            record=_record(),
            raw_content=BODY,
            normalization_version="alpaca-price-bars-v1",
        )

    with engine.connect() as connection:
        assert (
            connection.execute(select(func.count()).select_from(raw_data_object)).scalar_one() == 0
        )
        assert (
            connection.execute(select(func.count()).select_from(ingestion_raw_link)).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                select(func.count()).select_from(normalization_dispatch)
            ).scalar_one()
            == 0
        )
    engine.dispose()


def test_committed_raw_data_survives_a_crash_before_dispatch(isolated_database_url: str) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    job_id = _job_id(engine)
    raw_store = RecordingRawStore()
    writer = RawWriter(engine=engine, raw_store=raw_store)

    raw_id = writer.write(
        job_id=job_id,
        record=_record(),
        raw_content=BODY,
        normalization_version="alpaca-price-bars-v1",
    )

    published: list[tuple[UUID, str]] = []
    assert raw_store.keys
    with engine.connect() as connection:
        assert (
            connection.execute(select(func.count()).select_from(ingestion_raw_link)).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                select(func.count()).select_from(normalization_dispatch)
            ).scalar_one()
            == 1
        )

    assert (
        dispatch_pending_normalization(
            engine,
            publish=lambda queued_raw_id, version: published.append((queued_raw_id, version)),
            now=NOW + timedelta(seconds=1),
        )
        == 1
    )
    assert published == [(raw_id, "alpaca-price-bars-v1")]
    assert normalize_dispatched_record(
        engine,
        raw_id=raw_id,
        normalization_version="alpaca-price-bars-v1",
    )
    assert not normalize_dispatched_record(
        engine,
        raw_id=raw_id,
        normalization_version="alpaca-price-bars-v1",
    )
    with engine.connect() as connection:
        normalized = connection.execute(
            select(normalized_record.c.record_key, normalized_record.c.payload)
        ).one()
        assert normalized == ("NVDA", {"symbol": "NVDA", "close": "182.10"})
    assert (
        dispatch_pending_normalization(
            engine,
            publish=lambda queued_raw_id, version: published.append((queued_raw_id, version)),
            now=NOW + timedelta(seconds=2),
        )
        == 0
    )
    engine.dispose()


def test_dispatch_failure_is_retried_from_postgres_without_sleep(
    isolated_database_url: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    job_id = _job_id(engine)
    raw_id = RawWriter(engine=engine, raw_store=RecordingRawStore()).write(
        job_id=job_id,
        record=_record(),
        raw_content=BODY,
        normalization_version="alpaca-price-bars-v1",
    )
    attempts = 0

    def fail_once(queued_raw_id: UUID, version: str) -> None:
        nonlocal attempts
        attempts += 1
        assert (queued_raw_id, version) == (raw_id, "alpaca-price-bars-v1")
        if attempts == 1:
            raise TimeoutError("broker unavailable")

    assert dispatch_pending_normalization(engine, publish=fail_once, now=NOW) == 0
    assert (
        dispatch_pending_normalization(
            engine,
            publish=fail_once,
            now=NOW + timedelta(seconds=59),
        )
        == 0
    )
    assert (
        dispatch_pending_normalization(
            engine,
            publish=fail_once,
            now=NOW + timedelta(minutes=1),
        )
        == 1
    )
    assert attempts == 2
    engine.dispose()
