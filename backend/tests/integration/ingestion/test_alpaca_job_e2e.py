from __future__ import annotations

import hashlib
import json
from base64 import b64encode
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from celery.contrib.testing.worker import start_worker  # type: ignore[import-untyped]
from minio import Minio
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from stock_platform.application.market_data.policy import EntitlementSnapshot
from stock_platform.application.market_data.repositories import PostgresMarketDataRepository
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.ingestion.models import (
    DataPurpose,
    FeedType,
    IngestionErrorClass,
    MarketDataCoverage,
    MarketSession,
)
from stock_platform.infrastructure.db.models.tables import (
    data_quality_observation,
    ingestion_attempt,
    ingestion_cursor,
    ingestion_job,
    ingestion_raw_link,
    market_bar,
    news_article,
    normalization_dispatch,
    normalization_rejection,
    normalized_record,
    raw_data_object,
)
from stock_platform.infrastructure.ingestion.job_store import IngestionJobStore
from stock_platform.infrastructure.providers.alpaca_stream import (
    AlpacaStreamReplayWriter,
    alpaca_stream_object_key,
)
from stock_platform.infrastructure.providers.base import (
    ProviderBatch,
    ProviderRateLimit,
    ProviderTransportError,
)
from stock_platform.infrastructure.providers.object_store import MinioRawObjectStore
from stock_platform.settings import Settings
from stock_platform.workers import ingestion_tasks
from stock_platform.workers.alpaca_stream_supervisor import (
    alpaca_stream_recovery_object,
    replay_archived_stream_batches,
)
from stock_platform.workers.celery_app import celery_app
from stock_platform.workers.ingestion_tasks import (
    BarTimeframe,
    dispatch_queued_alpaca_jobs,
    execute_alpaca_ingestion_job,
)
from stock_platform.workers.portfolio_tasks import load_paper_execution_bars
from stock_platform.workers.schedules import schedule_alpaca_backfills

NOW = datetime(2026, 8, 24, 16, tzinfo=UTC)


def test_normalization_outbox_recovery_persists_typed_alpaca_fact(
    isolated_database_url: str,
    isolated_minio_store: MinioRawObjectStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    job_id = _enqueue(engine)
    original = ingestion_tasks.normalize_dispatched_record

    def crash_after_raw_commit(*_args: object, **_kwargs: object) -> bool:
        raise RuntimeError("simulated crash before normalization")

    monkeypatch.setattr(ingestion_tasks, "normalize_dispatched_record", crash_after_raw_commit)
    with pytest.raises(RuntimeError, match="simulated crash"):
        ingestion_tasks._persist_alpaca_batch(
            engine=engine,
            raw_store=isolated_minio_store,
            job_id=job_id,
            batch=_batch(
                b'{"bars":[{"t":"2026-08-21T15:00:00Z","o":"180","h":"181",'
                b'"l":"179","c":"180.5","v":"100"}],"symbol":"NVDA"}',
                token=None,
            ),
            coverage=MarketDataCoverage.IEX,
            timeframe="1Min",
            request_identity=str(job_id),
            now=NOW,
        )
    monkeypatch.setattr(ingestion_tasks, "normalize_dispatched_record", original)

    with engine.connect() as connection:
        raw_id = connection.execute(select(raw_data_object.c.id)).scalar_one()
        assert connection.execute(select(func.count()).select_from(market_bar)).scalar_one() == 0
        assert connection.execute(select(normalization_dispatch.c.state)).scalar_one() == "PENDING"
    with engine.begin() as connection:
        dispatch = connection.execute(select(normalization_dispatch)).mappings().one()
        connection.execute(
            normalized_record.insert().values(
                raw_data_object_id=raw_id,
                record_type=dispatch["record_type"],
                record_key=dispatch["record_key"],
                normalization_version=dispatch["normalization_version"],
                payload=dispatch["normalized_payload"],
            )
        )

    ingestion_tasks.run_normalization_task(
        engine,
        raw_id=raw_id,
        normalization_version="alpaca-bars-v1",
        now=NOW,
        raw_store=isolated_minio_store,
    )
    with engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(market_bar)).scalar_one() == 1
    engine.dispose()


def test_rest_schema_drift_keeps_raw_object_and_rejection(
    isolated_database_url: str,
    isolated_minio_store: MinioRawObjectStore,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    job_id = _enqueue(engine)
    with pytest.raises(ValueError, match="invalid JSON"):
        ingestion_tasks._persist_alpaca_batch(
            engine=engine,
            raw_store=isolated_minio_store,
            job_id=job_id,
            batch=_batch(b'{"bars":[', token=None),
            coverage=MarketDataCoverage.IEX,
            timeframe="1Min",
            request_identity=str(job_id),
            now=NOW,
        )

    assert len(isolated_minio_store.list_keys("live/ALPACA/price_bars/")) == 1
    with engine.connect() as connection:
        assert (
            connection.execute(select(func.count()).select_from(raw_data_object)).scalar_one() == 1
        )
        assert (
            connection.execute(
                select(func.count()).select_from(normalization_rejection)
            ).scalar_one()
            == 1
        )
    engine.dispose()


def test_rest_semantic_schema_drift_keeps_raw_object_and_rejection(
    isolated_database_url: str,
    isolated_minio_store: MinioRawObjectStore,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    job_id = _enqueue(engine)
    body = b'{"bars":[{"S":"NVDA","t":"not-a-date","o":180,"h":182,"l":179,"c":181,"v":1000}]}'
    with pytest.raises(ValueError):
        ingestion_tasks._persist_alpaca_batch(
            engine=engine,
            raw_store=isolated_minio_store,
            job_id=job_id,
            batch=_batch(body, token=None),
            coverage=MarketDataCoverage.IEX,
            timeframe="1Min",
            request_identity=str(job_id),
            now=NOW,
        )

    assert len(isolated_minio_store.list_keys("live/ALPACA/price_bars/")) == 1
    with engine.connect() as connection:
        assert (
            connection.execute(select(func.count()).select_from(raw_data_object)).scalar_one() == 1
        )
        assert (
            connection.execute(
                select(func.count()).select_from(normalization_rejection)
            ).scalar_one()
            == 1
        )
    engine.dispose()


@pytest.mark.parametrize("tamper", ["missing-provider", "valid-body"])
def test_recovery_rejects_tampered_envelope_and_records_schema_drift(
    isolated_database_url: str,
    isolated_minio_store: MinioRawObjectStore,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    job_id = _enqueue(engine)
    original = ingestion_tasks.normalize_dispatched_record

    def defer_normalization(*_args: object, **_kwargs: object) -> bool:
        raise RuntimeError("defer normalization")

    monkeypatch.setattr(ingestion_tasks, "normalize_dispatched_record", defer_normalization)
    with pytest.raises(RuntimeError, match="defer normalization"):
        ingestion_tasks._persist_alpaca_batch(
            engine=engine,
            raw_store=isolated_minio_store,
            job_id=job_id,
            batch=_batch(PAGE_1.body, token=None),
            coverage=MarketDataCoverage.IEX,
            timeframe="1Min",
            request_identity=str(job_id),
            now=NOW,
        )
    monkeypatch.setattr(ingestion_tasks, "normalize_dispatched_record", original)

    with engine.connect() as connection:
        raw_row = connection.execute(select(raw_data_object)).mappings().one()
    envelope = json.loads(isolated_minio_store.get(raw_row["raw_object_key"]))
    if tamper == "missing-provider":
        envelope.pop("provider")
    else:
        replacement = PAGE_1.body.replace(b'"c":"180.5"', b'"c":"999.0"')
        envelope["body_base64"] = b64encode(replacement).decode("ascii")
        envelope["body_sha256"] = hashlib.sha256(replacement).hexdigest()
    isolated_minio_store.put(
        raw_row["raw_object_key"],
        json.dumps(envelope).encode(),
        "application/json",
    )

    assert not ingestion_tasks.run_normalization_task(
        engine,
        raw_id=raw_row["id"],
        normalization_version="alpaca-bars-v1",
        now=NOW,
        raw_store=isolated_minio_store,
    )
    with engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count()).select_from(normalization_rejection)
            ).scalar_one()
            == 1
        )
        assert connection.execute(select(func.count()).select_from(market_bar)).scalar_one() == 0
    engine.dispose()


def test_websocket_schema_drift_keeps_raw_object_and_rejection(
    isolated_database_url: str,
    isolated_minio_store: MinioRawObjectStore,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    with pytest.raises(ValueError, match="invalid JSON"):
        AlpacaStreamReplayWriter(engine=engine, raw_store=isolated_minio_store).persist_batch(
            b'[{"T":"b"',
            received_at=NOW,
            coverage=MarketDataCoverage.IEX,
        )

    assert len(isolated_minio_store.list_keys("live/ALPACA/stream/iex/")) == 1
    with engine.connect() as connection:
        assert (
            connection.execute(select(func.count()).select_from(raw_data_object)).scalar_one() == 1
        )
        assert (
            connection.execute(
                select(func.count()).select_from(normalization_rejection)
            ).scalar_one()
            == 1
        )
    engine.dispose()


def test_registered_celery_task_executes_through_redis_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoked = Event()
    expected_job_id = uuid4()
    queue = f"ingestion-e2e-{uuid4().hex}"

    def execute_probe(**kwargs: object) -> bool:
        assert kwargs["job_id"] == expected_job_id
        invoked.set()
        return True

    monkeypatch.setattr(
        "stock_platform.workers.ingestion_tasks.execute_alpaca_ingestion_job",
        execute_probe,
    )
    with start_worker(
        celery_app,
        perform_ping_check=False,
        pool="solo",
        queues=[queue],
    ):
        celery_app.send_task(
            "stock_platform.workers.ingestion_tasks.run_alpaca_ingestion_job",
            args=[str(expected_job_id)],
            queue=queue,
        )
        assert invoked.wait(timeout=10), "Redis/Celery worker did not execute the registered task"


def test_ingestion_low_worker_runs_full_minio_postgres_pipeline(
    isolated_database_url: str,
    isolated_minio_store: MinioRawObjectStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    runtime_now = datetime.now(UTC).replace(microsecond=0)
    event_base = datetime(2026, 8, 21, 15, tzinfo=UTC)
    job_id = _enqueue(
        engine,
        start=event_base,
        end=event_base + timedelta(minutes=2),
    )
    base_pages = (
        _batch(
            (
                '{"bars":[{"t":"'
                + event_base.isoformat()
                + '","o":"180","h":"181","l":"179","c":"180.5","v":"100"}],'
                '"symbol":"NVDA","next_page_token":"page-2"}'
            ).encode(),
            token="page-2",
        ),
        _batch(
            (
                '{"bars":[{"t":"'
                + (event_base + timedelta(minutes=1)).isoformat()
                + '","o":"180.5","h":"181.5","l":"180","c":"181","v":"120"}],'
                '"symbol":"NVDA","next_page_token":null}'
            ).encode(),
            token=None,
        ),
    )
    runtime_pages: tuple[ProviderBatch, ...] = tuple(
        ProviderBatch(
            provider=page.provider,
            feed_type=page.feed_type,
            symbol=page.symbol,
            query_as_of=runtime_now,
            observed_at=runtime_now,
            body=page.body,
            headers=page.headers,
            next_page_token=page.next_page_token,
            rate_limit=page.rate_limit,
        )
        for page in base_pages
    )

    class RuntimeTransport(PaginatedTransport):
        def fetch_window(self, *args: object, **kwargs: object) -> ProviderBatch:
            assert kwargs["start"] == event_base
            assert kwargs["end"] == event_base + timedelta(minutes=2)
            return runtime_pages[0] if kwargs.get("page_token") is None else runtime_pages[1]

    settings = Settings(
        environment="paper",
        database_url=isolated_database_url,
        minio_bucket=isolated_minio_store._bucket,
        alpaca_data_key="test-key",
        alpaca_data_secret="test-secret",
        alpaca_entitlement_coverage="IEX",
        alpaca_entitlement_version="operator-verified-v1",
    )
    monkeypatch.setattr(ingestion_tasks, "Settings", lambda: settings)
    monkeypatch.setattr(
        "stock_platform.infrastructure.providers.alpaca.AlpacaProvider",
        lambda **_kwargs: RuntimeTransport(),
    )

    with start_worker(
        celery_app,
        perform_ping_check=False,
        pool="solo",
        queues=["ingestion-low"],
    ):
        celery_app.send_task(
            "stock_platform.workers.ingestion_tasks.run_alpaca_ingestion_job",
            args=[str(job_id)],
        )
        deadline = monotonic() + 10
        state = "QUEUED"
        while monotonic() < deadline:
            with engine.connect() as connection:
                state = str(
                    connection.execute(
                        select(ingestion_job.c.state).where(ingestion_job.c.id == job_id)
                    ).scalar_one()
                )
            if state == "SUCCEEDED":
                break
            sleep(0.05)

    assert state == "SUCCEEDED"
    with engine.connect() as connection:
        assert (
            connection.execute(select(func.count()).select_from(raw_data_object)).scalar_one() == 2
        )
        assert connection.execute(select(func.count()).select_from(market_bar)).scalar_one() == 2
    assert len(isolated_minio_store.list_keys("live/ALPACA/price_bars/")) == 2
    engine.dispose()


def _alembic_config(database_url: str) -> Config:
    config = Config(str(Path(__file__).parents[3] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


@pytest.fixture
def isolated_minio_store() -> Iterator[MinioRawObjectStore]:
    settings = Settings(environment="test")
    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    bucket = f"alpaca-e2e-{uuid4().hex}"
    store = MinioRawObjectStore(client=client, bucket=bucket)
    try:
        yield store
    finally:
        for item in client.list_objects(bucket, recursive=True):
            if item.object_name is not None:
                client.remove_object(bucket, item.object_name)
        client.remove_bucket(bucket)


def _batch(body: bytes, *, token: str | None) -> ProviderBatch:
    return ProviderBatch(
        provider="ALPACA",
        feed_type=FeedType.PRICE_BARS,
        symbol=Symbol("NVDA"),
        query_as_of=NOW,
        observed_at=NOW,
        body=body,
        headers={"X-Alpaca-Data-Feed": "SIP"},
        next_page_token=token,
        rate_limit=ProviderRateLimit(limit=200, remaining=199),
    )


PAGE_1 = _batch(
    b'{"bars":[{"t":"2026-08-24T15:00:00Z","o":"180.0","h":"181.0","l":"179.5","c":"180.5","v":"100"}],"symbol":"NVDA","next_page_token":"page-2"}',
    token="page-2",
)
PAGE_2 = _batch(
    b'{"bars":[{"t":"2026-08-24T15:01:00Z","o":"180.5","h":"181.5","l":"180.0","c":"181.0","v":"120"}],"symbol":"NVDA","next_page_token":null}',
    token=None,
)


class PaginatedTransport:
    def __init__(self, *, fail_once_on: str | None = None) -> None:
        self.calls: list[str | None] = []
        self._fail_once_on = fail_once_on

    def fetch_window(
        self,
        feed_type: FeedType,
        symbol: str,
        *,
        start: datetime,
        end: datetime,
        timeframe: str | None,
        coverage: str,
        page_token: str | None = None,
    ) -> ProviderBatch:
        assert feed_type is FeedType.PRICE_BARS
        assert symbol == "NVDA"
        assert timeframe == "1Min"
        assert coverage == "IEX"
        self.calls.append(page_token)
        if self._fail_once_on is not None and page_token == self._fail_once_on:
            self._fail_once_on = None
            raise ProviderTransportError(
                error_class=IngestionErrorClass.RATE_LIMIT,
                status_code=429,
                retry_after=timedelta(seconds=60),
            )
        return PAGE_1 if page_token is None else PAGE_2


def _enqueue(
    engine: object,
    *,
    dataset: FeedType = FeedType.PRICE_BARS,
    timeframe: BarTimeframe | None = BarTimeframe.MINUTE,
    start: datetime = NOW - timedelta(minutes=2),
    end: datetime = NOW,
    required_coverage: MarketDataCoverage = MarketDataCoverage.IEX,
    entitlement_coverage: frozenset[MarketDataCoverage] = frozenset({MarketDataCoverage.IEX}),
    sip_delay: timedelta | None = None,
) -> UUID:
    entitlement = EntitlementSnapshot(
        provider="ALPACA",
        coverage=entitlement_coverage,
        overnight=False,
        sip_delay=(
            sip_delay or timedelta(0) if MarketDataCoverage.SIP in entitlement_coverage else None
        ),
        observed_at=NOW,
        version="alpaca-entitlement-test-v1",
    )
    scheduled = schedule_alpaca_backfills(
        IngestionJobStore(engine),  # type: ignore[arg-type]
        symbol="NVDA",
        dataset=dataset,
        timeframe=timeframe,
        start=start,
        end=end,
        purpose=DataPurpose.RESEARCH,
        required_coverage=required_coverage,
        session=MarketSession.REGULAR,
        entitlement=entitlement,
        now=NOW,
    )
    return scheduled.job_ids[0]


def test_company_news_quality_does_not_inherit_sip_coverage_or_delay(
    isolated_database_url: str,
    isolated_minio_store: MinioRawObjectStore,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    job_id = _enqueue(
        engine,
        dataset=FeedType.COMPANY_NEWS,
        timeframe=None,
        required_coverage=MarketDataCoverage.SIP,
        entitlement_coverage=frozenset({MarketDataCoverage.SIP}),
        sip_delay=timedelta(minutes=15),
    )

    class NewsTransport(PaginatedTransport):
        def fetch_window(self, *args: object, **kwargs: object) -> ProviderBatch:
            return ProviderBatch(
                provider="ALPACA",
                feed_type=FeedType.COMPANY_NEWS,
                symbol=Symbol("NVDA"),
                query_as_of=NOW,
                observed_at=NOW - timedelta(minutes=12),
                body=(
                    b'{"news":[{"id":"news-1","symbols":["NVDA"],'
                    b'"headline":"Recorded headline","created_at":"2026-08-24T15:47:00Z",'
                    b'"observed_at":"2026-08-24T15:48:00Z","source":"fixture"}]}'
                ),
                headers={},
                next_page_token=None,
                rate_limit=ProviderRateLimit(),
            )

    assert execute_alpaca_ingestion_job(
        engine=engine,
        raw_store=isolated_minio_store,
        transport=NewsTransport(),
        job_id=job_id,
        now=NOW,
        worker_id="news-quality-worker",
    )
    with engine.connect() as connection:
        row = connection.execute(select(data_quality_observation)).mappings().one()
        assert row["status"] == "DEGRADED"
        assert row["coverage"] is None
        assert row["delay"] == timedelta(0)
        assert row["freshness"] == timedelta(minutes=12)
    engine.dispose()


def test_identical_iex_and_sip_bodies_remain_separate_fact_series(
    isolated_database_url: str,
    isolated_minio_store: MinioRawObjectStore,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    coverages = frozenset({MarketDataCoverage.IEX, MarketDataCoverage.SIP})
    iex_job = _enqueue(
        engine,
        required_coverage=MarketDataCoverage.IEX,
        entitlement_coverage=coverages,
    )
    sip_job = _enqueue(
        engine,
        required_coverage=MarketDataCoverage.SIP,
        entitlement_coverage=coverages,
    )

    class SameBodyTransport(PaginatedTransport):
        def fetch_window(self, *args: object, **kwargs: object) -> ProviderBatch:
            return PAGE_2

    assert execute_alpaca_ingestion_job(
        engine=engine,
        raw_store=isolated_minio_store,
        transport=SameBodyTransport(),
        job_id=iex_job,
        now=NOW,
        worker_id="iex-worker",
    )
    assert execute_alpaca_ingestion_job(
        engine=engine,
        raw_store=isolated_minio_store,
        transport=SameBodyTransport(),
        job_id=sip_job,
        now=NOW,
        worker_id="sip-worker",
    )
    with engine.connect() as connection:
        assert (
            connection.execute(select(func.count()).select_from(raw_data_object)).scalar_one() == 2
        )
        assert (
            connection.execute(select(func.count()).select_from(normalized_record)).scalar_one()
            == 2
        )
        assert connection.execute(select(func.count()).select_from(market_bar)).scalar_one() == 2
        assert set(connection.execute(select(market_bar.c.coverage)).scalars()) == {"IEX", "SIP"}
    engine.dispose()


def test_sip_quality_uses_frozen_entitlement_delay(
    isolated_database_url: str,
    isolated_minio_store: MinioRawObjectStore,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    job_id = _enqueue(
        engine,
        required_coverage=MarketDataCoverage.SIP,
        entitlement_coverage=frozenset({MarketDataCoverage.SIP}),
        sip_delay=timedelta(minutes=15),
    )

    class DelayedSipTransport(PaginatedTransport):
        def fetch_window(self, *args: object, **kwargs: object) -> ProviderBatch:
            return ProviderBatch(
                provider=PAGE_2.provider,
                feed_type=PAGE_2.feed_type,
                symbol=PAGE_2.symbol,
                query_as_of=PAGE_2.query_as_of,
                observed_at=NOW - timedelta(minutes=17),
                body=PAGE_2.body,
                headers=PAGE_2.headers,
                next_page_token=None,
                rate_limit=PAGE_2.rate_limit,
            )

    assert execute_alpaca_ingestion_job(
        engine=engine,
        raw_store=isolated_minio_store,
        transport=DelayedSipTransport(),
        job_id=job_id,
        now=NOW,
        worker_id="delayed-sip-worker",
    )
    with engine.connect() as connection:
        row = connection.execute(select(data_quality_observation)).mappings().one()
        assert row["status"] == "PASS"
        assert row["delay"] == timedelta(minutes=15)
        assert row["freshness"] == timedelta(minutes=17)
    engine.dispose()


def test_celery_job_persists_all_pages_through_minio_and_postgres(
    isolated_database_url: str,
    isolated_minio_store: MinioRawObjectStore,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    job_id = _enqueue(engine)
    transport = PaginatedTransport()
    published: list[UUID] = []

    assert (
        dispatch_queued_alpaca_jobs(
            engine,
            publish=published.append,
            now=NOW,
        )
        == 1
    )
    assert published == [job_id]

    result = execute_alpaca_ingestion_job(
        engine=engine,
        raw_store=isolated_minio_store,
        transport=transport,
        job_id=job_id,
        now=NOW,
        worker_id="celery-test-worker",
    )
    with engine.connect() as diagnostic_connection:
        diagnostic_job = diagnostic_connection.execute(select(ingestion_job)).mappings().one()
        diagnostic_attempt = (
            diagnostic_connection.execute(select(ingestion_attempt)).mappings().one()
        )
    assert result, (
        diagnostic_job["state"],
        diagnostic_job["request_payload"],
        diagnostic_job["next_attempt_at"],
        diagnostic_attempt["error_detail"],
    )

    assert transport.calls == [None, "page-2"]
    assert len(isolated_minio_store.list_keys("live/ALPACA/price_bars/")) == 2
    with engine.connect() as connection:
        assert (
            connection.execute(select(func.count()).select_from(raw_data_object)).scalar_one() == 2
        )
        assert (
            connection.execute(select(func.count()).select_from(normalized_record)).scalar_one()
            == 2
        )
        assert connection.execute(select(func.count()).select_from(market_bar)).scalar_one() == 2
        assert connection.execute(select(func.count()).select_from(news_article)).scalar_one() == 0
        assert connection.execute(select(ingestion_job.c.state)).scalar_one() == "SUCCEEDED"
        cursor = connection.execute(select(ingestion_cursor)).mappings().one()
        assert cursor["generation"] == 2
        assert cursor["scope_key"] == str(job_id)
        assert cursor["cursor_payload"]["next_page_token"] is None
        assert set(connection.execute(select(market_bar.c.coverage)).scalars()) == {"IEX"}
    engine.dispose()


def test_identical_empty_responses_across_windows_preserve_request_observations(
    isolated_database_url: str,
    isolated_minio_store: MinioRawObjectStore,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    first_job = _enqueue(engine)
    second_job = _enqueue(
        engine,
        start=NOW + timedelta(minutes=1),
        end=NOW + timedelta(minutes=3),
    )
    empty = _batch(b'{"bars":[],"symbol":"NVDA","next_page_token":null}', token=None)

    class EmptyTransport(PaginatedTransport):
        def fetch_window(self, *args: object, **kwargs: object) -> ProviderBatch:
            return empty

    assert execute_alpaca_ingestion_job(
        engine=engine,
        raw_store=isolated_minio_store,
        transport=EmptyTransport(),
        job_id=first_job,
        now=NOW,
        worker_id="empty-worker-1",
    )
    assert execute_alpaca_ingestion_job(
        engine=engine,
        raw_store=isolated_minio_store,
        transport=EmptyTransport(),
        job_id=second_job,
        now=NOW + timedelta(minutes=3),
        worker_id="empty-worker-2",
    )
    with engine.connect() as connection:
        assert (
            connection.execute(select(func.count()).select_from(raw_data_object)).scalar_one() == 2
        )
        assert (
            connection.execute(select(func.count()).select_from(ingestion_raw_link)).scalar_one()
            == 2
        )
    engine.dispose()


def test_expired_lease_is_rejected_before_raw_persistence(
    isolated_database_url: str,
    isolated_minio_store: MinioRawObjectStore,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    job_id = _enqueue(engine)

    assert not execute_alpaca_ingestion_job(
        engine=engine,
        raw_store=isolated_minio_store,
        transport=PaginatedTransport(),
        job_id=job_id,
        now=NOW,
        worker_id="stale-worker",
        clock=lambda: NOW + timedelta(minutes=11),
    )
    with engine.connect() as connection:
        assert (
            connection.execute(select(func.count()).select_from(raw_data_object)).scalar_one() == 0
        )
        assert connection.execute(select(ingestion_job.c.state)).scalar_one() == "RUNNING"
    engine.dispose()


def test_expired_lease_cannot_advance_cursor_after_fact_commit(
    isolated_database_url: str,
    isolated_minio_store: MinioRawObjectStore,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    job_id = _enqueue(engine)
    readings = iter((NOW, NOW, NOW + timedelta(minutes=11)))

    assert not execute_alpaca_ingestion_job(
        engine=engine,
        raw_store=isolated_minio_store,
        transport=PaginatedTransport(),
        job_id=job_id,
        now=NOW,
        worker_id="stale-after-write",
        clock=lambda: next(readings),
    )
    with engine.connect() as connection:
        assert (
            connection.execute(select(func.count()).select_from(raw_data_object)).scalar_one() == 1
        )
        assert (
            connection.execute(select(func.count()).select_from(ingestion_cursor)).scalar_one() == 0
        )
    engine.dispose()


def test_quality_failure_is_retried_before_cursor_advances(
    isolated_database_url: str,
    isolated_minio_store: MinioRawObjectStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    store = IngestionJobStore(engine)
    job_id = _enqueue(engine)
    original = ingestion_tasks._persist_alpaca_quality

    def fail_quality(**_kwargs: object) -> None:
        raise SQLAlchemyError("simulated quality database failure")

    monkeypatch.setattr(ingestion_tasks, "_persist_alpaca_quality", fail_quality)
    assert not execute_alpaca_ingestion_job(
        engine=engine,
        raw_store=isolated_minio_store,
        transport=PaginatedTransport(),
        job_id=job_id,
        now=NOW,
        worker_id="quality-failure-worker",
    )
    with engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count()).select_from(data_quality_observation)
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(select(func.count()).select_from(ingestion_cursor)).scalar_one() == 0
        )
        assert connection.execute(select(ingestion_job.c.state)).scalar_one() == "RETRY_SCHEDULED"

    assert store.requeue_due(now=NOW + timedelta(minutes=1)) == 1
    monkeypatch.setattr(ingestion_tasks, "_persist_alpaca_quality", original)
    assert execute_alpaca_ingestion_job(
        engine=engine,
        raw_store=isolated_minio_store,
        transport=PaginatedTransport(),
        job_id=job_id,
        now=NOW + timedelta(minutes=1),
        worker_id="quality-retry-worker",
    )
    with engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count()).select_from(data_quality_observation)
            ).scalar_one()
            == 2
        )
        assert connection.execute(select(ingestion_cursor.c.generation)).scalar_one() == 2
        assert connection.execute(select(ingestion_job.c.state)).scalar_one() == "SUCCEEDED"
    engine.dispose()


def test_failed_second_page_resumes_from_durable_cursor_without_refetching_first_page(
    isolated_database_url: str,
    isolated_minio_store: MinioRawObjectStore,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    store = IngestionJobStore(engine)
    job_id = _enqueue(engine)
    first_attempt = PaginatedTransport(fail_once_on="page-2")

    assert not execute_alpaca_ingestion_job(
        engine=engine,
        raw_store=isolated_minio_store,
        transport=first_attempt,
        job_id=job_id,
        now=NOW,
        worker_id="celery-test-worker-1",
    )
    assert first_attempt.calls == [None, "page-2"]
    assert store.requeue_due(now=NOW + timedelta(seconds=61)) == 1

    resumed = PaginatedTransport()
    assert execute_alpaca_ingestion_job(
        engine=engine,
        raw_store=isolated_minio_store,
        transport=resumed,
        job_id=job_id,
        now=NOW + timedelta(seconds=61),
        worker_id="celery-test-worker-2",
    )
    assert resumed.calls == ["page-2"]
    with engine.connect() as connection:
        assert (
            connection.execute(select(func.count()).select_from(raw_data_object)).scalar_one() == 2
        )
        assert connection.execute(select(func.count()).select_from(market_bar)).scalar_one() == 2
        assert connection.execute(select(ingestion_job.c.state)).scalar_one() == "SUCCEEDED"
    engine.dispose()


def test_object_store_failure_is_recorded_as_retryable_job_state(
    isolated_database_url: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    job_id = _enqueue(engine)

    class FailingObjectStore:
        def put(self, object_key: str, content: bytes, content_type: str) -> None:
            raise OSError("fixture object store unavailable")

    assert not execute_alpaca_ingestion_job(
        engine=engine,
        raw_store=FailingObjectStore(),
        transport=PaginatedTransport(),
        job_id=job_id,
        now=NOW,
        worker_id="celery-test-worker",
    )
    with engine.connect() as connection:
        job = connection.execute(select(ingestion_job)).mappings().one()
        attempt = connection.execute(select(ingestion_attempt)).mappings().one()
    assert job["state"] == "RETRY_SCHEDULED"
    assert attempt["error_class"] == "TEMPORARY_OBJECT_STORE"
    engine.dispose()


def test_schema_drift_preserves_raw_lineage_and_dead_letters_the_job(
    isolated_database_url: str,
    isolated_minio_store: MinioRawObjectStore,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    job_id = _enqueue(engine)

    class DriftedTransport(PaginatedTransport):
        def fetch_window(self, *args: object, **kwargs: object) -> ProviderBatch:
            return _batch(b'{"unexpected":{}}', token=None)

    assert not execute_alpaca_ingestion_job(
        engine=engine,
        raw_store=isolated_minio_store,
        transport=DriftedTransport(),
        job_id=job_id,
        now=NOW,
        worker_id="celery-test-worker",
    )
    with engine.connect() as connection:
        job = connection.execute(select(ingestion_job)).mappings().one()
        attempt = connection.execute(select(ingestion_attempt)).mappings().one()
        assert (
            connection.execute(select(func.count()).select_from(raw_data_object)).scalar_one() == 1
        )
        assert connection.execute(select(func.count()).select_from(market_bar)).scalar_one() == 0
    assert job["state"] == "DEAD_LETTER"
    assert attempt["error_class"] == "SCHEMA_DRIFT"
    engine.dispose()


@pytest.mark.parametrize("event_type", ("t", "q", "s", "u"))
def test_websocket_source_events_are_idempotently_replayable_from_minio_and_postgres(
    isolated_database_url: str,
    isolated_minio_store: MinioRawObjectStore,
    event_type: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    raw = (f'{{"T":"{event_type}","S":"NVDA","t":"2026-08-24T15:00:00Z","p":"180.5"}}').encode()
    replay = AlpacaStreamReplayWriter(engine=engine, raw_store=isolated_minio_store)

    first = replay.persist(raw, received_at=NOW, coverage=MarketDataCoverage.IEX)
    second = replay.persist(
        raw, received_at=NOW + timedelta(minutes=1), coverage=MarketDataCoverage.IEX
    )

    assert first == second
    with engine.connect() as connection:
        assert (
            connection.execute(select(func.count()).select_from(raw_data_object)).scalar_one() == 1
        )
        assert (
            connection.execute(select(func.count()).select_from(normalized_record)).scalar_one()
            == 1
        )
        assert connection.execute(select(func.count()).select_from(market_bar)).scalar_one() == 0
    assert len(isolated_minio_store.list_keys("live/ALPACA/stream/")) == 1
    engine.dispose()


def test_websocket_wire_batch_preserves_coverage_and_persists_typed_bar(
    isolated_database_url: str,
    isolated_minio_store: MinioRawObjectStore,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    raw = (
        b'[ {"T":"b","S":"NVDA","t":"2026-08-24T15:00:00Z",'
        b'"o":180,"h":182,"l":179,"c":181,"v":1000}, '
        b'{"T":"b","S":"AAPL","t":"2026-08-24T15:00:00Z",'
        b'"o":220,"h":222,"l":219,"c":221,"v":900}, '
        b'{"T":"q","S":"NVDA","t":"2026-08-24T15:00:01Z","bp":180} ]'
    )
    replay = AlpacaStreamReplayWriter(engine=engine, raw_store=isolated_minio_store)

    iex = replay.persist_batch(raw, received_at=NOW, coverage=MarketDataCoverage.IEX)
    sip = replay.persist_batch(raw, received_at=NOW, coverage=MarketDataCoverage.SIP)
    assert (
        replay.persist_batch(
            raw,
            received_at=NOW + timedelta(minutes=1),
            coverage=MarketDataCoverage.SIP,
        )
        == sip
    )

    assert len(set(iex + sip)) == 2
    with engine.connect() as connection:
        raws = connection.execute(select(raw_data_object)).mappings().all()
        assert len(raws) == 2
        assert {row["feed_type"] for row in raws} == {
            "alpaca_stream_batch_iex",
            "alpaca_stream_batch_sip",
        }
        assert (
            connection.execute(select(func.count()).select_from(normalized_record)).scalar_one()
            == 6
        )
        bars = connection.execute(select(market_bar)).mappings().all()
        assert {row["coverage"] for row in bars} == {"IEX", "SIP"}
        assert {(row["symbol"], row["coverage"]) for row in bars} == {
            ("NVDA", "IEX"),
            ("NVDA", "SIP"),
            ("AAPL", "IEX"),
            ("AAPL", "SIP"),
        }
        iex_visible = PostgresMarketDataRepository(connection).as_of(
            symbol="NVDA",
            feed_type=FeedType.PRICE_BARS,
            decision_time=NOW,
            coverage=MarketDataCoverage.IEX,
        )
        assert {record.payload["coverage"] for record in iex_visible.records} == {"IEX"}
        execution_bars = load_paper_execution_bars(
            connection,
            symbols=("NVDA",),
            decision_time=datetime(2026, 8, 24, 14, 59, tzinfo=UTC),
            observed_at=NOW,
        )
        assert len(execution_bars) == 1
        assert execution_bars[0].event_time == datetime(2026, 8, 24, 15, tzinfo=UTC)
    assert len(isolated_minio_store.list_keys("live/ALPACA/stream/")) == 2
    engine.dispose()


def test_paper_pit_uses_regular_session_and_latest_visible_bar_revision(
    isolated_database_url: str,
    isolated_minio_store: MinioRawObjectStore,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    replay = AlpacaStreamReplayWriter(engine=engine, raw_store=isolated_minio_store)
    batches = (
        (
            b'{"T":"b","S":"NVDA","t":"2026-08-24T14:58:00Z",'
            b'"o":179,"h":180,"l":178,"c":179.5,"v":800}',
            datetime(2026, 8, 24, 14, 58, 30, tzinfo=UTC),
        ),
        (
            b'{"T":"b","S":"NVDA","t":"2026-08-24T15:00:00Z",'
            b'"o":180,"h":182,"l":179,"c":181,"v":1000}',
            datetime(2026, 8, 24, 15, 0, 10, tzinfo=UTC),
        ),
        (
            b'{"T":"b","S":"NVDA","t":"2026-08-24T15:00:00Z",'
            b'"o":181,"h":183,"l":180,"c":182,"v":1100}',
            datetime(2026, 8, 24, 15, 1, tzinfo=UTC),
        ),
        (
            b'{"T":"b","S":"NVDA","t":"2026-08-24T22:00:00Z",'
            b'"o":190,"h":191,"l":189,"c":190.5,"v":500}',
            datetime(2026, 8, 24, 22, 0, 10, tzinfo=UTC),
        ),
    )
    for raw, received_at in batches:
        replay.persist_batch(raw, received_at=received_at, coverage=MarketDataCoverage.SIP)

    observation = datetime(2026, 8, 24, 23, tzinfo=UTC)
    with engine.connect() as connection:
        bars = load_paper_execution_bars(
            connection,
            symbols=("NVDA",),
            decision_time=datetime(2026, 8, 24, 14, 59, tzinfo=UTC),
            observed_at=observation,
        )
        research = PostgresMarketDataRepository(connection).as_of(
            symbol="NVDA",
            feed_type=FeedType.PRICE_BARS,
            decision_time=observation,
            coverage=MarketDataCoverage.SIP,
        )

    assert [bar.event_time.hour for bar in bars] == [14, 15]
    assert bars[-1].open == Decimal("181")
    assert {record.payload["session"] for record in research.records} == {"REGULAR"}
    assert {record.event_time.hour for record in research.records} == {14, 15}
    engine.dispose()


def test_minio_orphan_recovery_preserves_first_received_at_and_skips_referenced(
    isolated_database_url: str,
    isolated_minio_store: MinioRawObjectStore,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    raw = (
        b'{"T":"b","S":"NVDA","t":"2026-08-24T15:00:00Z","o":180,"h":182,"l":179,"c":181,"v":1000}'
    )
    first_received_at = datetime(2026, 8, 24, 15, 0, 5, tzinfo=UTC)
    raw_key = alpaca_stream_object_key(raw, coverage=MarketDataCoverage.SIP)
    recovery_key, recovery_envelope = alpaca_stream_recovery_object(
        raw,
        coverage=MarketDataCoverage.SIP,
        received_at=first_received_at,
    )
    isolated_minio_store.put(raw_key, raw, "application/json")
    isolated_minio_store.put(recovery_key, recovery_envelope, "application/json")
    writer = AlpacaStreamReplayWriter(engine=engine, raw_store=isolated_minio_store)

    def referenced(key: str) -> bool:
        with engine.connect() as connection:
            return (
                connection.execute(
                    select(raw_data_object.c.id).where(raw_data_object.c.raw_object_key == key)
                ).scalar_one_or_none()
                is not None
            )

    def persist(_task: str, args: list[str]) -> None:
        writer.persist_batch(
            args[0].encode(),
            received_at=datetime.fromisoformat(args[1]),
            coverage=MarketDataCoverage(args[2]),
        )

    first = replay_archived_stream_batches(
        isolated_minio_store,
        publish=persist,
        is_referenced=referenced,
    )
    second = replay_archived_stream_batches(
        isolated_minio_store,
        publish=persist,
        is_referenced=referenced,
    )

    assert first.replayed == 1
    assert second.replayed == 0
    with engine.connect() as connection:
        raw_row = connection.execute(select(raw_data_object)).mappings().one()
        bar_row = connection.execute(select(market_bar)).mappings().one()
    assert raw_row["available_at"] == first_received_at
    assert bar_row["available_at"] == first_received_at
    engine.dispose()
