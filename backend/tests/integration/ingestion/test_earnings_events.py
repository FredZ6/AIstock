import json
from base64 import b64decode
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, insert, inspect, select, update
from sqlalchemy.exc import DBAPIError
from stock_platform.application.ingestion.normalizers.alpha_vantage import EarningsEvent
from stock_platform.domain.ingestion.models import FeedType
from stock_platform.infrastructure.db.models.tables import (
    data_quality_observation,
    earnings_event,
    ingestion_job,
    normalized_record,
    raw_data_object,
    security_identifier_version,
)
from stock_platform.infrastructure.db.security_seed import seed_security_master
from stock_platform.infrastructure.ingestion.fact_store import PostgresEarningsEventStore
from stock_platform.infrastructure.providers.alpha_vantage import (
    AlphaVantageProvider,
    PostgresAlphaSymbolResolver,
)
from stock_platform.infrastructure.providers.base import HttpRequest, HttpResponse
from stock_platform.workers.ingestion_tasks import execute_alpha_earnings_ingestion_job
from stock_platform.workers.schedules import schedule_alpha_earnings_job


def _migrate(database_url: str) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def test_earnings_events_append_changed_dates_and_preserve_snapshot_lineage(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    observed = (datetime(2026, 8, 26, tzinfo=UTC), datetime(2026, 8, 27, tzinfo=UTC))
    raw_ids: list[UUID] = []
    normalized_ids: list[UUID] = []
    with engine.begin() as connection:
        seed_security_master(connection)
        security_id = connection.execute(
            select(security_identifier_version.c.security_id).where(
                security_identifier_version.c.identifier_value == "NVDA"
            )
        ).scalar_one()
        for index, available_at in enumerate(observed):
            raw_id = connection.execute(
                insert(raw_data_object)
                .values(
                    provider="ALPHA_VANTAGE",
                    feed_type="earnings_calendar",
                    event_time=available_at,
                    available_at=available_at,
                    ingested_at=available_at,
                    content_hash=str(index + 6) * 64,
                    raw_object_key=(
                        f"live/ALPHA_VANTAGE/earnings_calendar/{str(index + 6) * 64}.csv"
                    ),
                )
                .returning(raw_data_object.c.id)
            ).scalar_one()
            normalized_id = connection.execute(
                insert(normalized_record)
                .values(
                    raw_data_object_id=raw_id,
                    record_type="earnings_event",
                    record_key=f"NVDA:2026-10-31:{index}",
                    normalization_version="alpha-earnings-v1",
                    payload={"symbol": "NVDA"},
                )
                .returning(normalized_record.c.id)
            ).scalar_one()
            raw_ids.append(raw_id)
            normalized_ids.append(normalized_id)
        store = PostgresEarningsEventStore(connection)
        first = EarningsEvent.from_values(
            symbol="NVDA",
            provider_symbol="NVDA",
            event_date="2026-11-19",
            fiscal_date_end="2026-10-31",
            estimate="1.2345",
            currency="USD",
            available_at=observed[0],
            payload={"name": "NVIDIA"},
        )
        revised = EarningsEvent.from_values(
            symbol="NVDA",
            provider_symbol="NVDA",
            event_date="2026-11-20",
            fiscal_date_end="2026-10-31",
            estimate="1.2500",
            currency="USD",
            available_at=observed[1],
            payload={"name": "NVIDIA"},
        )
        first_id = store.persist_event(
            security_id=security_id,
            raw_id=raw_ids[0],
            normalized_id=normalized_ids[0],
            event=first,
        )
        assert (
            store.persist_event(
                security_id=security_id,
                raw_id=raw_ids[0],
                normalized_id=normalized_ids[0],
                event=first,
            )
            == first_id
        )
        revised_id = store.persist_event(
            security_id=security_id,
            raw_id=raw_ids[1],
            normalized_id=normalized_ids[1],
            event=revised,
        )
        rows = (
            connection.execute(select(earnings_event).order_by(earnings_event.c.available_at))
            .mappings()
            .all()
        )
        assert (
            connection.execute(select(func.count()).select_from(earnings_event)).scalar_one() == 2
        )
        assert rows[0]["estimate"] == Decimal("1.2345")
        assert rows[1]["id"] == revised_id
        assert rows[1]["supersedes_id"] == first_id
        assert rows[1]["event_date"] == date(2026, 11, 20)
        assert rows[1]["raw_data_object_id"] == raw_ids[1]
    with engine.connect() as connection, pytest.raises(DBAPIError, match="append-only"):
        connection.execute(update(earnings_event).values(event_date=date(2026, 11, 21)))
    inspector = inspect(engine)
    assert "earnings_event" in inspector.get_table_names()
    assert "earnings_calendar_snapshot" not in inspector.get_table_names()
    engine.dispose()


def test_alpha_daily_job_persists_full_csv_then_filtered_typed_events(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    now = datetime(2026, 8, 26, 6, 30, tzinfo=UTC)
    body = (
        b"symbol,name,reportDate,fiscalDateEnding,estimate,currency\n"
        b"NVDA,NVIDIA,2026-11-19,2026-10-31,1.2345,USD\n"
        b"TSM,TSMC,2026-10-15,2026-09-30,2.50,USD\n"
        b"AAPL,Apple,2026-10-29,2026-09-30,1.99,USD\n"
    )

    class RecordingRawStore:
        writes: list[tuple[str, bytes, str]] = []

        def put(self, object_key: str, content: bytes, content_type: str) -> None:
            self.writes.append((object_key, content, content_type))

    with engine.begin() as connection:
        seed_security_master(connection)
        aliases = PostgresAlphaSymbolResolver(connection).mapping(now)
    assert aliases["NVDA"] == "NVDA"
    assert "AAPL" not in aliases

    job_id = schedule_alpha_earnings_job(engine, now=now)
    assert schedule_alpha_earnings_job(engine, now=now) == job_id
    raw_store = RecordingRawStore()
    provider = AlphaVantageProvider(
        api_key="fixture-key",
        transport=lambda request: (
            HttpResponse(status_code=200, headers={"Content-Type": "text/csv"}, body=body)
            if isinstance(request, HttpRequest)
            else None
        ),
        clock=lambda: now,
    )

    assert execute_alpha_earnings_ingestion_job(
        engine=engine,
        raw_store=raw_store,
        transport=provider,
        job_id=job_id,
        now=now,
        worker_id="test-alpha-worker",
    )
    assert len(raw_store.writes) == 1
    first_envelope = json.loads(raw_store.writes[0][1])
    assert b64decode(first_envelope["body_base64"]) == body
    assert raw_store.writes[0][2] == "application/json"
    with engine.connect() as connection:
        assert (
            connection.execute(select(func.count()).select_from(raw_data_object)).scalar_one() == 1
        )
        assert (
            connection.execute(select(func.count()).select_from(normalized_record)).scalar_one()
            == 2
        )
        assert (
            connection.execute(select(func.count()).select_from(earnings_event)).scalar_one() == 2
        )
        assert (
            connection.execute(
                select(ingestion_job.c.state).where(ingestion_job.c.id == job_id)
            ).scalar_one()
            == "SUCCEEDED"
        )
        quality_rows = (
            connection.execute(
                select(data_quality_observation).where(
                    data_quality_observation.c.provider == "ALPHA_VANTAGE",
                    data_quality_observation.c.dataset == FeedType.EARNINGS_CALENDAR.value,
                )
            )
            .mappings()
            .all()
        )
        assert len(quality_rows) == 2
        assert {row["status"] for row in quality_rows} == {"PASS"}

    next_day = datetime(2026, 8, 27, 6, 30, tzinfo=UTC)
    next_job_id = schedule_alpha_earnings_job(engine, now=next_day)
    next_provider = AlphaVantageProvider(
        api_key="fixture-key",
        transport=lambda request: HttpResponse(
            status_code=200,
            headers={"Content-Type": "text/csv"},
            body=body,
        ),
        clock=lambda: next_day,
    )
    assert execute_alpha_earnings_ingestion_job(
        engine=engine,
        raw_store=raw_store,
        transport=next_provider,
        job_id=next_job_id,
        now=next_day,
        worker_id="test-alpha-worker",
    )
    assert len(raw_store.writes) == 2
    with engine.connect() as connection:
        assert (
            connection.execute(select(func.count()).select_from(raw_data_object)).scalar_one() == 2
        )
        assert (
            connection.execute(select(func.count()).select_from(normalized_record)).scalar_one()
            == 4
        )
        assert (
            connection.execute(select(func.count()).select_from(earnings_event)).scalar_one() == 4
        )
    engine.dispose()


def test_alpha_job_without_credentials_terminates_explicitly(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    now = datetime(2026, 8, 26, 6, 30, tzinfo=UTC)
    job_id = schedule_alpha_earnings_job(engine, now=now)

    class NoWrites:
        def put(self, object_key: str, content: bytes, content_type: str) -> None:
            raise AssertionError("raw storage must not run without credentials")

    assert not execute_alpha_earnings_ingestion_job(
        engine=engine,
        raw_store=NoWrites(),
        transport=AlphaVantageProvider(api_key=None),
        job_id=job_id,
        now=now,
        worker_id="test-alpha-worker",
    )
    with engine.connect() as connection:
        assert (
            connection.execute(
                select(ingestion_job.c.state).where(ingestion_job.c.id == job_id)
            ).scalar_one()
            == "DEAD_LETTER"
        )
    engine.dispose()


def test_alpha_object_store_failure_schedules_durable_retry(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    now = datetime(2026, 8, 26, 6, 30, tzinfo=UTC)
    job_id = schedule_alpha_earnings_job(engine, now=now)
    body = (
        b"symbol,name,reportDate,fiscalDateEnding,estimate,currency\n"
        b"NVDA,NVIDIA,2026-11-19,2026-10-31,1.2345,USD\n"
    )

    class FailingRawStore:
        def put(self, object_key: str, content: bytes, content_type: str) -> None:
            raise RuntimeError("MinIO unavailable")

    provider = AlphaVantageProvider(
        api_key="fixture-key",
        transport=lambda request: HttpResponse(status_code=200, headers={}, body=body),
        clock=lambda: now,
    )
    assert not execute_alpha_earnings_ingestion_job(
        engine=engine,
        raw_store=FailingRawStore(),
        transport=provider,
        job_id=job_id,
        now=now,
        worker_id="test-alpha-worker",
    )
    with engine.connect() as connection:
        row = connection.execute(
            select(ingestion_job.c.state, ingestion_job.c.next_attempt_at).where(
                ingestion_job.c.id == job_id
            )
        ).one()
        assert row.state == "RETRY_SCHEDULED"
        assert row.next_attempt_at is not None
    engine.dispose()
