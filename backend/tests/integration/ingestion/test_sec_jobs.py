from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from minio import Minio
from sqlalchemy import create_engine, func, select
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.ingestion.models import FeedType
from stock_platform.infrastructure.db.models.tables import (
    data_quality_observation,
    financial_fact,
    ingestion_job,
    raw_data_object,
    sec_filing,
)
from stock_platform.infrastructure.db.security_seed import seed_security_master
from stock_platform.infrastructure.providers.base import ProviderBatch, ProviderRateLimit
from stock_platform.infrastructure.providers.object_store import MinioRawObjectStore
from stock_platform.settings import Settings
from stock_platform.workers.ingestion_tasks import execute_sec_ingestion_job
from stock_platform.workers.schedules import schedule_sec_daily_jobs

FIXTURES = Path("backend/tests/contract/providers/fixtures/sec")
NOW = datetime(2026, 8, 26, 22, tzinfo=UTC)


def _migrate(database_url: str) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


class FailingRawStore:
    def put(self, object_key: str, content: bytes, content_type: str) -> None:
        raise OSError("object store unavailable")


class InMemoryRawStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, object_key: str, content: bytes, content_type: str) -> None:
        self.objects[object_key] = content


class FixtureSecTransport:
    def __init__(self, *, observed_at: datetime = NOW) -> None:
        self.observed_at = observed_at

    def _batch(self, feed_type: FeedType, symbol: str, body: bytes) -> ProviderBatch:
        return ProviderBatch(
            provider="SEC",
            feed_type=feed_type,
            symbol=Symbol(symbol),
            query_as_of=NOW,
            observed_at=self.observed_at,
            body=body,
            headers={},
            next_page_token=None,
            rate_limit=ProviderRateLimit(),
        )

    def fetch_batch(self, feed_type: FeedType, symbol: str, as_of: datetime) -> ProviderBatch:
        fixture = "submissions.json" if feed_type is FeedType.FILINGS else "companyfacts.json"
        return self._batch(feed_type, symbol, (FIXTURES / fixture).read_bytes())

    def fetch_historical_submissions(
        self, symbol: str, *, file_name: str, as_of: datetime
    ) -> ProviderBatch:
        return self._batch(FeedType.FILINGS, symbol, (FIXTURES / file_name).read_bytes())

    def fetch_filing_document(
        self,
        symbol: str,
        *,
        accession_number: str,
        primary_document: str,
        as_of: datetime,
    ) -> ProviderBatch:
        return self._batch(
            FeedType.FILINGS, symbol, (FIXTURES / "filing_document.html").read_bytes()
        )


@pytest.fixture
def isolated_minio_store() -> Iterator[MinioRawObjectStore]:
    settings = Settings(environment="test")
    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    bucket = f"sec-e2e-{uuid4().hex}"
    store = MinioRawObjectStore(client=client, bucket=bucket)
    try:
        yield store
    finally:
        for item in client.list_objects(bucket, recursive=True):
            if item.object_name is not None:
                client.remove_object(bucket, item.object_name)
        client.remove_bucket(bucket)


def test_sec_jobs_are_idempotently_scheduled_and_persist_raw_filing_and_financial_lineage(
    isolated_database_url: str,
    isolated_minio_store: MinioRawObjectStore,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    with engine.begin() as connection:
        seed_security_master(connection)

    assert schedule_sec_daily_jobs(engine, now=NOW) == 11
    assert schedule_sec_daily_jobs(engine, now=NOW) == 11
    with engine.connect() as connection:
        assert (
            connection.execute(select(func.count()).select_from(ingestion_job)).scalar_one() == 11
        )
        jobs = {
            str(row["dataset"]): row["id"]
            for row in connection.execute(
                select(ingestion_job).where(
                    ingestion_job.c.provider == "SEC",
                    ingestion_job.c.request_payload["request"]["symbol"].astext == "NVDA",
                )
            ).mappings()
        }

    transport = FixtureSecTransport()
    assert execute_sec_ingestion_job(
        engine=engine,
        raw_store=isolated_minio_store,
        transport=transport,
        job_id=UUID(str(jobs[FeedType.FILINGS.value])),
        now=NOW,
        worker_id="test-sec",
        clock=lambda: NOW,
    )
    with engine.connect() as connection:
        company_facts_job_id = connection.execute(
            select(ingestion_job.c.id).where(
                ingestion_job.c.provider == "SEC",
                ingestion_job.c.dataset == FeedType.COMPANY_FACTS.value,
                ingestion_job.c.request_payload["request"]["symbol"].astext == "NVDA",
            )
        ).scalar_one()
    assert execute_sec_ingestion_job(
        engine=engine,
        raw_store=isolated_minio_store,
        transport=transport,
        job_id=company_facts_job_id,
        now=NOW,
        worker_id="test-sec",
        clock=lambda: NOW,
    )

    with engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(sec_filing)).scalar_one() == 3
        assert (
            connection.execute(select(func.count()).select_from(financial_fact)).scalar_one() == 4
        )
        # The three identical recorded filing documents share one content-addressed object.
        assert (
            connection.execute(select(func.count()).select_from(raw_data_object)).scalar_one() == 4
        )
        assert (
            connection.execute(
                select(func.count())
                .select_from(financial_fact)
                .where(
                    financial_fact.c.raw_data_object_id.is_not(None),
                    financial_fact.c.normalized_record_id.is_not(None),
                    financial_fact.c.sec_filing_id.is_not(None),
                )
            ).scalar_one()
            == 4
        )
        quality_rows = (
            connection.execute(
                select(data_quality_observation).where(
                    data_quality_observation.c.provider == "SEC",
                    data_quality_observation.c.dataset == FeedType.FILINGS.value,
                )
            )
            .mappings()
            .all()
        )
        assert len(quality_rows) == 3
        assert {row["status"] for row in quality_rows} == {"PASS"}
    assert len(isolated_minio_store.list_keys("live/SEC/")) == 4

    next_day = NOW.replace(day=27)
    assert schedule_sec_daily_jobs(engine, now=next_day) == 11
    with engine.connect() as connection:
        next_jobs = {
            str(row["dataset"]): row["id"]
            for row in connection.execute(
                select(ingestion_job).where(
                    ingestion_job.c.provider == "SEC",
                    ingestion_job.c.created_at == next_day,
                    ingestion_job.c.request_payload["request"]["symbol"].astext == "NVDA",
                )
            ).mappings()
        }
    next_transport = FixtureSecTransport(observed_at=next_day)
    assert execute_sec_ingestion_job(
        engine=engine,
        raw_store=isolated_minio_store,
        transport=next_transport,
        job_id=UUID(str(next_jobs[FeedType.FILINGS.value])),
        now=next_day,
        worker_id="test-sec",
        clock=lambda: next_day,
    )
    with engine.connect() as connection:
        next_company_facts_job_id = connection.execute(
            select(ingestion_job.c.id).where(
                ingestion_job.c.provider == "SEC",
                ingestion_job.c.dataset == FeedType.COMPANY_FACTS.value,
                ingestion_job.c.created_at == next_day,
                ingestion_job.c.request_payload["request"]["symbol"].astext == "NVDA",
            )
        ).scalar_one()
    assert execute_sec_ingestion_job(
        engine=engine,
        raw_store=isolated_minio_store,
        transport=next_transport,
        job_id=next_company_facts_job_id,
        now=next_day,
        worker_id="test-sec",
        clock=lambda: next_day,
    )
    with engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(sec_filing)).scalar_one() == 3
        assert (
            connection.execute(select(func.count()).select_from(financial_fact)).scalar_one() == 4
        )
        repeated_quality = (
            connection.execute(
                select(data_quality_observation).where(
                    data_quality_observation.c.provider == "SEC",
                    data_quality_observation.c.dataset == FeedType.FILINGS.value,
                )
            )
            .mappings()
            .all()
        )
        assert len(repeated_quality) == 6
        assert {row["status"] for row in repeated_quality} == {"PASS"}


def test_sec_response_observed_after_claim_preserves_timestamp_order(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    with engine.begin() as connection:
        seed_security_master(connection)
    schedule_sec_daily_jobs(engine, now=NOW)
    with engine.connect() as connection:
        job_id = connection.execute(
            select(ingestion_job.c.id).where(
                ingestion_job.c.provider == "SEC",
                ingestion_job.c.dataset == FeedType.FILINGS.value,
                ingestion_job.c.request_payload["request"]["symbol"].astext == "NVDA",
            )
        ).scalar_one()
    observed_at = NOW.replace(minute=1)
    assert execute_sec_ingestion_job(
        engine=engine,
        raw_store=InMemoryRawStore(),
        transport=FixtureSecTransport(observed_at=observed_at),
        job_id=job_id,
        now=NOW,
        worker_id="test-sec",
        clock=lambda: observed_at,
    )
    with engine.connect() as connection:
        timestamp_rows = connection.execute(
            select(raw_data_object.c.available_at, raw_data_object.c.ingested_at).where(
                raw_data_object.c.provider == "SEC"
            )
        ).all()
        assert timestamp_rows
        assert all(available_at <= ingested_at for available_at, ingested_at in timestamp_rows)
    engine.dispose()


def test_sec_object_store_failure_schedules_retry_without_postgres_raw_lineage(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    with engine.begin() as connection:
        seed_security_master(connection)
    schedule_sec_daily_jobs(engine, now=NOW)
    with engine.connect() as connection:
        job_id = connection.execute(
            select(ingestion_job.c.id).where(
                ingestion_job.c.provider == "SEC",
                ingestion_job.c.dataset == FeedType.FILINGS.value,
                ingestion_job.c.request_payload["request"]["symbol"].astext == "NVDA",
            )
        ).scalar_one()

    assert not execute_sec_ingestion_job(
        engine=engine,
        raw_store=FailingRawStore(),
        transport=FixtureSecTransport(),
        job_id=job_id,
        now=NOW,
        worker_id="test-sec",
        clock=lambda: NOW,
    )
    with engine.connect() as connection:
        state = connection.execute(
            select(ingestion_job.c.state).where(ingestion_job.c.id == job_id)
        ).scalar_one()
        assert state == "RETRY_SCHEDULED"
        assert (
            connection.execute(select(func.count()).select_from(raw_data_object)).scalar_one() == 0
        )
    engine.dispose()


def test_sec_worker_stops_before_raw_write_when_lease_heartbeat_is_lost(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    with engine.begin() as connection:
        seed_security_master(connection)
    schedule_sec_daily_jobs(engine, now=NOW)
    with engine.connect() as connection:
        job_id = connection.execute(
            select(ingestion_job.c.id).where(
                ingestion_job.c.provider == "SEC",
                ingestion_job.c.dataset == FeedType.FILINGS.value,
                ingestion_job.c.request_payload["request"]["symbol"].astext == "NVDA",
            )
        ).scalar_one()
    timestamps = iter((NOW, NOW + timedelta(minutes=16)))

    assert not execute_sec_ingestion_job(
        engine=engine,
        raw_store=InMemoryRawStore(),
        transport=FixtureSecTransport(),
        job_id=job_id,
        now=NOW,
        worker_id="test-sec",
        clock=lambda: next(timestamps),
    )
    with engine.connect() as connection:
        assert (
            connection.execute(select(func.count()).select_from(raw_data_object)).scalar_one() == 0
        )
    engine.dispose()


def test_sec_worker_cas_rejects_postgres_lineage_when_lease_expires_during_minio_put(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    with engine.begin() as connection:
        seed_security_master(connection)
    schedule_sec_daily_jobs(engine, now=NOW)
    with engine.connect() as connection:
        job_id = connection.execute(
            select(ingestion_job.c.id).where(
                ingestion_job.c.provider == "SEC",
                ingestion_job.c.dataset == FeedType.FILINGS.value,
                ingestion_job.c.request_payload["request"]["symbol"].astext == "NVDA",
            )
        ).scalar_one()
    current = [NOW]

    class ExpiringRawStore(InMemoryRawStore):
        def put(self, object_key: str, content: bytes, content_type: str) -> None:
            super().put(object_key, content, content_type)
            current[0] = NOW + timedelta(minutes=16)

    raw_store = ExpiringRawStore()
    assert not execute_sec_ingestion_job(
        engine=engine,
        raw_store=raw_store,
        transport=FixtureSecTransport(),
        job_id=job_id,
        now=NOW,
        worker_id="test-sec",
        clock=lambda: current[0],
    )
    assert len(raw_store.objects) == 1
    with engine.connect() as connection:
        assert (
            connection.execute(select(func.count()).select_from(raw_data_object)).scalar_one() == 0
        )
    engine.dispose()
