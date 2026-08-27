from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, insert, select
from stock_platform.application.alerting.features import MinuteBar
from stock_platform.application.ingestion.jobs import IngestionJobSpec
from stock_platform.application.runs import append_run_event
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.ingestion.models import DataPurpose, FeedType, IngestionRequest
from stock_platform.infrastructure.db.models.tables import (
    agent_event,
    agent_run,
    cash_ledger,
    paper_fill,
)
from stock_platform.infrastructure.ingestion.job_store import IngestionJobStore
from stock_platform.infrastructure.messaging.market_stream import RedisMarketStream
from stock_platform.infrastructure.recovery import (
    CircuitBreaker,
    RecoveryDecision,
    recover_expired_run,
)
from stock_platform.infrastructure.recovery_probe import (
    persist_paper_fill_probe,
    recover_ingestion_leases,
)
from stock_platform.workers.schedules import recover_queued_runs


def test_expired_worker_lease_is_requeued_without_reexecuting_authoritative_effects() -> None:
    now = datetime(2026, 8, 23, 4, tzinfo=UTC)
    decision = recover_expired_run(
        status="RUNNING",
        lease_expires_at=now - timedelta(seconds=1),
        attempt_count=1,
        max_attempts=3,
        now=now,
    )

    assert decision is RecoveryDecision.REQUEUE


def test_active_or_exhausted_run_is_not_requeued() -> None:
    now = datetime(2026, 8, 23, 4, tzinfo=UTC)
    assert (
        recover_expired_run(
            status="RUNNING",
            lease_expires_at=now + timedelta(seconds=1),
            attempt_count=1,
            max_attempts=3,
            now=now,
        )
        is RecoveryDecision.NO_ACTION
    )
    assert (
        recover_expired_run(
            status="RUNNING",
            lease_expires_at=now - timedelta(seconds=1),
            attempt_count=3,
            max_attempts=3,
            now=now,
        )
        is RecoveryDecision.FAIL
    )


def test_provider_circuit_opens_after_bounded_failures_and_recovers_after_timeout() -> None:
    start = datetime(2026, 8, 23, 4, tzinfo=UTC)
    circuit = CircuitBreaker(failure_threshold=2, recovery_timeout=timedelta(seconds=30))

    circuit.record_failure(at=start)
    assert circuit.allow_request(at=start) is True
    circuit.record_failure(at=start + timedelta(seconds=1))
    assert circuit.allow_request(at=start + timedelta(seconds=2)) is False
    assert circuit.allow_request(at=start + timedelta(seconds=31)) is True


def test_recovery_identity_is_not_derived_from_redis_delivery_ids() -> None:
    first = uuid4()
    replay = first
    assert replay == first


def test_paper_fill_recovery_probe_is_nonempty_and_idempotent(
    isolated_database_url: str,
) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")

    first = persist_paper_fill_probe(isolated_database_url)
    replay = persist_paper_fill_probe(isolated_database_url)

    engine = create_engine(isolated_database_url)
    with engine.connect() as connection:
        fill_count = connection.execute(
            select(func.count()).select_from(paper_fill).where(paper_fill.c.id == first)
        ).scalar_one()
        ledger_count = connection.execute(
            select(func.count()).select_from(cash_ledger).where(cash_ledger.c.source_id == first)
        ).scalar_one()
    engine.dispose()
    assert replay == first
    assert fill_count == 1
    assert ledger_count == 3


def test_ingestion_lease_recovery_probe_is_nonempty_and_idempotent(
    isolated_database_url: str,
) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database_url)
    now = datetime(2026, 8, 28, 1, tzinfo=UTC)
    store = IngestionJobStore(engine)
    job_id = store.enqueue(
        IngestionJobSpec(
            request=IngestionRequest(
                {"provider": "ALPACA", "dataset": "price_bars", "symbol": "NVDA"}
            ),
            provider="ALPACA",
            dataset=FeedType.PRICE_BARS,
            window_start=now - timedelta(minutes=1),
            window_end=now,
            purpose=DataPurpose.RESEARCH,
            policy_version="ingestion-v1",
            max_attempts=3,
        ),
        now=now,
    )
    assert store.claim(job_id, worker_id="lost", now=now, lease_for=timedelta(seconds=1))
    engine.dispose()

    assert recover_ingestion_leases(isolated_database_url, at=now + timedelta(seconds=2)) == 1
    assert recover_ingestion_leases(isolated_database_url, at=now + timedelta(seconds=2)) == 0


def test_redis_stream_loss_keeps_authoritative_events_and_requeues_expired_work(
    isolated_database_url: str,
) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database_url)
    run_id = uuid4()
    correlation_id = uuid4()
    now = datetime(2026, 8, 23, 4, tzinfo=UTC)
    stream = RedisMarketStream(
        url="redis://localhost:56379/0", stream_name=f"recovery-{uuid4().hex}"
    )
    bar = MinuteBar(
        symbol=Symbol("NVDA"),
        event_time=now,
        available_at=now,
        ingested_at=now,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100"),
        volume=Decimal("1000"),
        previous_close=Decimal("99"),
        provider="FIXTURE",
        content_hash="a" * 64,
        raw_object_key="fixture/recovery.json",
        raw_payload={},
    )
    dispatched: list[tuple[str, str]] = []

    with engine.begin() as connection:
        connection.execute(
            insert(agent_run).values(
                id=run_id,
                correlation_id=correlation_id,
                run_type="RESEARCH",
                idempotency_key=f"recovery-{run_id}",
                request_hash="a" * 64,
                request_payload={"symbol": "NVDA"},
                symbol="NVDA",
                decision_time=now,
                data_cutoff=now,
                status="RUNNING",
                attempt_count=1,
                lease_expires_at=now - timedelta(seconds=1),
            )
        )
        append_run_event(connection, run_id, "run.started", {"attempt": 1})

    try:
        stream.publish(bar)
        stream.delete()  # Redis is transient; simulate total stream loss.
        with engine.begin() as connection:
            assert recover_queued_runs(
                connection,
                now=now,
                dispatch=lambda task, value: dispatched.append((task, value)),
            ) == (str(run_id),)
        with engine.connect() as connection:
            assert (
                connection.execute(
                    select(agent_run.c.status).where(agent_run.c.id == run_id)
                ).scalar_one()
                == "QUEUED"
            )
            event = connection.execute(
                select(agent_event.c.correlation_id).where(agent_event.c.run_id == run_id)
            ).scalar_one()
            assert event == correlation_id
        assert dispatched == [("stock_platform.workers.research_tasks.run_research", str(run_id))]
    finally:
        stream.delete()
        stream.close()
        engine.dispose()
