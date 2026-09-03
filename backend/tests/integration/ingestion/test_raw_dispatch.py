from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, insert, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from stock_platform.application.ingestion import raw_writer as raw_writer_module
from stock_platform.application.ingestion.jobs import IngestionJobSpec
from stock_platform.application.ingestion.raw_writer import RawObjectStoreUnavailable, RawWriter
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.ingestion.models import DataPurpose, FeedType, IngestionRequest
from stock_platform.infrastructure.db.models.tables import (
    ingestion_raw_link,
    normalization_dispatch,
    normalization_rejection,
    normalized_record,
    raw_data_object,
)
from stock_platform.infrastructure.ingestion.job_store import IngestionJobStore
from stock_platform.infrastructure.providers.base import ProviderRecord
from stock_platform.infrastructure.providers.persistence import PostgresProviderRecordStore
from stock_platform.workers import ingestion_tasks
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

    def list_keys(self, prefix: str = "") -> tuple[str, ...]:
        return tuple(key for key in self.keys if key.startswith(prefix))


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


def test_canonical_symbol_cannot_be_overridden_by_provider_payload(
    isolated_database_url: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)

    with engine.begin() as connection:
        PostgresProviderRecordStore(connection).persist(
            _record(payload={"symbol": "AAPL", "close": "182.10"}),
            "alpaca-price-bars-v1",
        )
        payload = connection.execute(select(normalized_record.c.payload)).scalar_one()

    assert payload["symbol"] == "NVDA"
    engine.dispose()


def test_later_observation_of_same_raw_bytes_reuses_first_observation(
    isolated_database_url: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    first = _record()
    later = replace(
        first,
        available_at=first.available_at + timedelta(minutes=5),
        ingested_at=first.ingested_at + timedelta(minutes=5),
    )

    with engine.begin() as connection:
        store = PostgresProviderRecordStore(connection)
        store.persist(first, "alpaca-price-bars-v1")
        store.persist(later, "alpaca-price-bars-v1")
        raw_row = connection.execute(
            select(raw_data_object.c.available_at, raw_data_object.c.ingested_at)
        ).one()

    assert raw_row == (first.available_at, first.ingested_at)
    engine.dispose()


def test_raw_writer_requires_object_storage_before_database_commit(
    isolated_database_url: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    job_id = _job_id(engine)
    writer = RawWriter(engine=engine, raw_store=RecordingRawStore(fail=True))

    with pytest.raises(RawObjectStoreUnavailable, match="raw object store write failed"):
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


def test_worker_can_normalize_before_dispatcher_commits_dispatched_state(
    isolated_database_url: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    RawWriter(engine=engine, raw_store=RecordingRawStore()).write(
        job_id=_job_id(engine),
        record=_record(),
        raw_content=BODY,
        normalization_version="alpaca-price-bars-v1",
    )
    worker_results: list[bool] = []

    assert (
        dispatch_pending_normalization(
            engine,
            publish=lambda queued_raw_id, version: worker_results.append(
                normalize_dispatched_record(
                    engine,
                    raw_id=queued_raw_id,
                    normalization_version=version,
                )
            ),
            now=NOW + timedelta(seconds=1),
        )
        == 1
    )
    assert worker_results == [True]
    with engine.connect() as connection:
        normalized_count = connection.execute(
            select(func.count()).select_from(normalized_record)
        ).scalar_one()
        assert normalized_count == 1
    engine.dispose()


def test_transient_normalization_failure_is_durably_requeued(
    isolated_database_url: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    raw_id = RawWriter(engine=engine, raw_store=RecordingRawStore()).write(
        job_id=_job_id(engine),
        record=_record(),
        raw_content=BODY,
        normalization_version="alpaca-price-bars-v1",
    )
    assert dispatch_pending_normalization(engine, publish=lambda *_: None, now=NOW) == 1
    handler = getattr(ingestion_tasks, "record_normalization_failure", None)
    assert handler is not None, "normalization failures need a durable PostgreSQL handler"

    state = handler(
        engine,
        raw_id=raw_id,
        normalization_version="alpaca-price-bars-v1",
        error=RuntimeError("temporary database failure"),
        now=NOW + timedelta(seconds=1),
        retry_after=timedelta(minutes=1),
        max_attempts=3,
    )

    assert state == "PENDING"
    with engine.connect() as connection:
        row = connection.execute(
            select(
                normalization_dispatch.c.state,
                normalization_dispatch.c.next_attempt_at,
                normalization_dispatch.c.last_error,
            )
        ).one()
    assert row == (
        "PENDING",
        NOW + timedelta(minutes=1, seconds=1),
        {"type": "RuntimeError"},
    )
    engine.dispose()


def test_immutable_normalization_conflict_is_quarantined_and_not_stranded(
    isolated_database_url: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    raw_id = RawWriter(engine=engine, raw_store=RecordingRawStore()).write(
        job_id=_job_id(engine),
        record=_record(),
        raw_content=BODY,
        normalization_version="alpaca-price-bars-v1",
    )
    assert dispatch_pending_normalization(engine, publish=lambda *_: None, now=NOW) == 1
    with engine.begin() as connection:
        connection.execute(
            insert(normalized_record).values(
                raw_data_object_id=raw_id,
                record_type=FeedType.PRICE_BARS.value,
                record_key="NVDA",
                normalization_version="alpaca-price-bars-v1",
                payload={"symbol": "NVDA", "close": "999.99"},
            )
        )
    runner = getattr(ingestion_tasks, "run_normalization_task", None)
    assert runner is not None, "normalization tasks need durable failure handling"

    assert not runner(
        engine,
        raw_id=raw_id,
        normalization_version="alpaca-price-bars-v1",
        now=NOW + timedelta(seconds=1),
    )
    with engine.connect() as connection:
        assert connection.execute(select(normalization_dispatch.c.state)).scalar_one() == "FAILED"
        assert (
            connection.execute(
                select(func.count()).select_from(normalization_rejection)
            ).scalar_one()
            == 1
        )
    engine.dispose()


def test_raw_writer_rejects_non_content_addressed_object_key(
    isolated_database_url: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    raw_store = RecordingRawStore()

    with pytest.raises(ValueError, match="content-addressed"):
        RawWriter(engine=engine, raw_store=raw_store).write(
            job_id=_job_id(engine),
            record=_record(object_key="live/ALPACA/price_bars/latest.json"),
            raw_content=BODY,
            normalization_version="alpaca-price-bars-v1",
        )

    assert raw_store.keys == []
    engine.dispose()


def test_database_failure_after_minio_is_reported_as_an_orphan(
    isolated_database_url: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    raw_store = RecordingRawStore()
    record = _record()

    with pytest.raises(IntegrityError):
        RawWriter(engine=engine, raw_store=raw_store).write(
            job_id=uuid4(),
            record=record,
            raw_content=BODY,
            normalization_version="alpaca-price-bars-v1",
        )

    reporter = getattr(raw_writer_module, "report_orphaned_raw_objects", None)
    assert reporter is not None, "MinIO objects without committed metadata must be reportable"
    assert reporter(engine, raw_store) == (record.raw_object_key,)
    with engine.connect() as connection:
        raw_count = connection.execute(
            select(func.count()).select_from(raw_data_object)
        ).scalar_one()
        assert raw_count == 0
    engine.dispose()


def test_orphan_report_ignores_operational_recovery_envelopes(
    isolated_database_url: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    raw_store = RecordingRawStore()
    raw_store.keys.extend(
        [
            "live/ALPACA/stream/iex/unreferenced.json",
            "live/ALPACA/stream-recovery/iex/envelope.json",
        ]
    )

    reporter = raw_writer_module.report_orphaned_raw_objects
    assert reporter(
        engine,
        raw_store,
        excluded_prefixes=("live/ALPACA/stream-recovery/",),
    ) == ("live/ALPACA/stream/iex/unreferenced.json",)
    engine.dispose()
