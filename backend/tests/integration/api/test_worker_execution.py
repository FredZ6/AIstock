from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import Event
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, insert, select, update
from sqlalchemy.engine import Connection, Engine, RowMapping
from sqlalchemy.exc import DBAPIError, IntegrityError
from stock_platform.application.events.sse import load_events
from stock_platform.application.runs import RetryableRunError, RunControl, execute_run
from stock_platform.infrastructure.db.models.tables import (
    agent_event,
    agent_run,
    cash_ledger,
    decision_diff,
    decision_outcome,
    decision_snapshot,
    evidence_gap,
    execution_policy_version,
    investment_thesis,
    market_bar,
    market_context_snapshot,
    normalized_record,
    paper_portfolio_config,
    raw_data_object,
    risk_decision,
    risk_policy_version,
    tool_call,
    weekly_review_run,
)
from stock_platform.infrastructure.providers.base import FeedType, ProviderStatus
from stock_platform.infrastructure.providers.fixture.loader import FixtureCatalog
from stock_platform.workers.portfolio_tasks import execute_portfolio_run
from stock_platform.workers.research_tasks import (
    PostgresResearchProvider,
    execute_market_monitor_run,
    execute_research_run,
)
from stock_platform.workers.review_tasks import _paper_prices, execute_weekly_review_run
from stock_platform.workers.schedules import recover_queued_runs


def _migrate(database_url: str) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def _queued_run(engine: Engine) -> UUID:
    run_id = uuid4()
    now = datetime(2026, 8, 21, 21, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            insert(agent_run).values(
                id=run_id,
                run_type="RESEARCH",
                idempotency_key=f"worker-{run_id}",
                request_hash="d" * 64,
                request_payload={"symbol": "NVDA"},
                symbol="NVDA",
                decision_time=now,
                data_cutoff=now,
                status="QUEUED",
            )
        )
    return run_id


def test_0023_backfills_type_specific_pins_and_complete_policy_content(
    isolated_database_url: str,
) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "0022_single_portfolio_guard")
    engine = create_engine(isolated_database_url)
    now = datetime(2026, 8, 21, tzinfo=UTC)
    with engine.begin() as connection:
        for run_type in ("RESEARCH", "PORTFOLIO", "ALERT_MONITOR", "WEEKLY_REVIEW"):
            connection.execute(
                insert(agent_run).values(
                    run_type=run_type,
                    idempotency_key=f"legacy-{run_type}",
                    request_hash=run_type,
                    request_payload={},
                    decision_time=now,
                    data_cutoff=now,
                )
            )
        connection.execute(
            insert(risk_policy_version).values(
                version="risk-v1", policy={"source": "task_specification"}
            )
        )
        connection.execute(
            insert(execution_policy_version).values(
                version="execution-v1", policy={"source": "task_specification"}
            )
        )
    command.upgrade(config, "head")
    with engine.connect() as connection:
        pins = {
            run_type: (prompt, model)
            for run_type, prompt, model in connection.execute(
                select(
                    agent_run.c.run_type,
                    agent_run.c.prompt_version,
                    agent_run.c.model_version,
                )
            )
        }
        assert pins == {
            "RESEARCH": ("prompt-v1", "fixture-v1"),
            "PORTFOLIO": ("portfolio-prompt-v1", "fixture-proposer-v1"),
            "ALERT_MONITOR": ("deterministic-alert-v1", "none"),
            "WEEKLY_REVIEW": ("weekly-review-prompt-v1", "model-v1"),
        }
        assert (
            "max_position_weight"
            in connection.execute(
                select(risk_policy_version.c.policy).where(
                    risk_policy_version.c.version == "risk-v1"
                )
            ).scalar_one()
        )
        assert (
            "volume_participation"
            in connection.execute(
                select(execution_policy_version.c.policy).where(
                    execution_policy_version.c.version == "execution-v1"
                )
            ).scalar_one()
        )
    engine.dispose()


def test_single_paper_portfolio_configuration_is_explicit_and_immutable(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    with engine.begin() as connection:
        row = connection.execute(select(paper_portfolio_config)).mappings().one()
        assert row["name"] == "default-paper"
        assert row["initial_cash"] == Decimal("100000")
        assert row["currency"] == "USD"
        insert_savepoint = connection.begin_nested()
        with pytest.raises(IntegrityError):
            connection.execute(
                insert(paper_portfolio_config).values(
                    id=uuid4(),
                    name="second-paper",
                    initial_cash=Decimal("1"),
                    currency="USD",
                )
            )
        insert_savepoint.rollback()
        update_savepoint = connection.begin_nested()
        with pytest.raises(DBAPIError, match="append-only"):
            connection.execute(
                update(paper_portfolio_config).values(initial_cash=Decimal("200000"))
            )
        update_savepoint.rollback()
    engine.dispose()


def test_admitted_run_policy_prompt_and_model_pins_are_database_immutable(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    run_id = _queued_run(engine)
    with engine.begin() as connection:
        row = connection.execute(select(agent_run).where(agent_run.c.id == run_id)).mappings().one()
        assert tuple(
            row[name]
            for name in (
                "research_scoring_policy_version",
                "risk_policy_version",
                "execution_policy_version",
                "confidence_policy_version",
                "prompt_version",
                "model_version",
            )
        ) == (
            "research-v1",
            "risk-v1",
            "execution-v1",
            "confidence-v1",
            "prompt-v1",
            "fixture-v1",
        )
        savepoint = connection.begin_nested()
        with pytest.raises(DBAPIError, match="run execution pins are immutable"):
            connection.execute(
                update(agent_run)
                .where(agent_run.c.id == run_id)
                .values(model_version="changed-model")
            )
        savepoint.rollback()
    engine.dispose()


def test_worker_executes_once_and_persists_lifecycle_events(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    run_id = _queued_run(engine)
    calls: list[str] = []

    def work(connection: Connection, _row: RowMapping, control: RunControl) -> None:
        calls.append("work")
        control.node_completed("fixture")

    assert execute_run(isolated_database_url, run_id, "RESEARCH", work) is True
    assert execute_run(isolated_database_url, run_id, "RESEARCH", work) is False
    with engine.connect() as connection:
        assert calls == ["work"]
        assert (
            connection.execute(
                select(agent_run.c.status).where(agent_run.c.id == run_id)
            ).scalar_one()
            == "COMPLETED"
        )
        assert connection.execute(
            select(agent_event.c.event_type)
            .where(agent_event.c.run_id == run_id)
            .order_by(agent_event.c.sequence)
        ).scalars().all() == ["run.started", "node.completed", "run.completed"]
    engine.dispose()


def test_worker_start_and_node_events_are_visible_before_work_commits(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    run_id = _queued_run(engine)

    def work(_connection: Connection, _row: RowMapping, control: RunControl) -> None:
        with engine.connect() as observer:
            assert (
                observer.execute(
                    select(agent_run.c.status).where(agent_run.c.id == run_id)
                ).scalar_one()
                == "RUNNING"
            )
            assert observer.execute(
                select(agent_event.c.event_type).where(agent_event.c.run_id == run_id)
            ).scalars().all() == ["run.started"]
        control.node_completed("visible-node")
        with engine.connect() as observer:
            assert observer.execute(
                select(agent_event.c.event_type)
                .where(agent_event.c.run_id == run_id)
                .order_by(agent_event.c.sequence)
            ).scalars().all() == ["run.started", "node.completed"]

    assert execute_run(isolated_database_url, run_id, "RESEARCH", work) is True
    engine.dispose()


def test_worker_failure_is_bounded_and_releases_admission_capacity(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    run_id = _queued_run(engine)

    def fail(_connection: Connection, _row: RowMapping, control: RunControl) -> None:
        control.node_completed("before-crash")
        raise RetryableRunError("worker crashed")

    for _ in range(3):
        with pytest.raises(RuntimeError, match="worker crashed"):
            execute_run(isolated_database_url, run_id, "RESEARCH", fail)
    with engine.connect() as connection:
        row = connection.execute(
            select(
                agent_run.c.status,
                agent_run.c.attempt_count,
                agent_run.c.last_error,
            ).where(agent_run.c.id == run_id)
        ).one()
        assert row.status == "FAILED"
        assert row.attempt_count == 3
        assert row.last_error == {"type": "RetryableRunError", "message": "worker failed"}
        assert (
            connection.execute(
                select(func.count())
                .select_from(agent_event)
                .where(
                    agent_event.c.run_id == run_id,
                    agent_event.c.event_type == "run.failed",
                )
            ).scalar_one()
            == 1
        )
    engine.dispose()


def test_worker_observes_concurrent_cancellation_at_node_boundary(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    run_id = _queued_run(engine)

    def work(_connection: Connection, _row: RowMapping, control: RunControl) -> None:
        with engine.begin() as canceller:
            changed = canceller.execute(
                update(agent_run)
                .where(agent_run.c.id == run_id, agent_run.c.status == "RUNNING")
                .values(status="CANCELLED")
            )
            assert changed.rowcount == 1
        control.node_completed("cancel-boundary")

    assert execute_run(isolated_database_url, run_id, "RESEARCH", work) is False
    with engine.connect() as connection:
        assert (
            connection.execute(
                select(agent_run.c.status).where(agent_run.c.id == run_id)
            ).scalar_one()
            == "CANCELLED"
        )
        assert connection.execute(
            select(agent_event.c.event_type)
            .where(agent_event.c.run_id == run_id)
            .order_by(agent_event.c.sequence)
        ).scalars().all() == ["run.started", "run.cancelled"]
    engine.dispose()


@pytest.mark.parametrize("stale_raises", [False, True])
def test_expired_attempt_cannot_complete_fail_or_cancel_a_reclaimed_run(
    isolated_database_url: str, stale_raises: bool
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    run_id = _queued_run(engine)
    first_started = Event()
    second_started = Event()
    release_first = Event()
    release_second = Event()

    def first_work(_connection: Connection, _row: RowMapping, _control: RunControl) -> None:
        first_started.set()
        assert release_first.wait(timeout=5)
        if stale_raises:
            raise RetryableRunError("stale attempt failed after reclaim")

    def second_work(_connection: Connection, _row: RowMapping, _control: RunControl) -> None:
        second_started.set()
        assert release_second.wait(timeout=5)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(execute_run, isolated_database_url, run_id, "RESEARCH", first_work)
        assert first_started.wait(timeout=5)
        with engine.begin() as connection:
            connection.execute(
                update(agent_run)
                .where(agent_run.c.id == run_id)
                .values(lease_expires_at=datetime(2026, 8, 21, tzinfo=UTC))
            )
            recover_queued_runs(
                connection,
                now=datetime(2026, 8, 22, tzinfo=UTC),
                dispatch=lambda _task, _run_id: None,
            )
        second = pool.submit(execute_run, isolated_database_url, run_id, "RESEARCH", second_work)
        assert second_started.wait(timeout=5)
        release_first.set()
        assert first.result(timeout=5) is False
        with engine.connect() as connection:
            row = connection.execute(
                select(agent_run.c.status, agent_run.c.attempt_count).where(
                    agent_run.c.id == run_id
                )
            ).one()
            assert row == ("RUNNING", 2)
            assert (
                connection.execute(
                    select(func.count())
                    .select_from(agent_event)
                    .where(
                        agent_event.c.run_id == run_id,
                        agent_event.c.event_type == "run.cancelled",
                    )
                ).scalar_one()
                == 0
            )
        release_second.set()
        assert second.result(timeout=5) is True

    with engine.connect() as connection:
        assert (
            connection.execute(
                select(agent_run.c.status).where(agent_run.c.id == run_id)
            ).scalar_one()
            == "COMPLETED"
        )
    engine.dispose()


def test_research_worker_runs_real_graph_once_with_ordered_events(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    run_id = uuid4()
    as_of = datetime(2026, 8, 16, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            insert(agent_run).values(
                id=run_id,
                run_type="RESEARCH",
                idempotency_key=f"research-worker-{run_id}",
                request_hash="e" * 64,
                request_payload={"symbol": "NVDA"},
                symbol="NVDA",
                decision_time=as_of,
                data_cutoff=as_of,
                status="QUEUED",
            )
        )

    assert execute_research_run(isolated_database_url, str(run_id)) is True
    assert execute_research_run(isolated_database_url, str(run_id)) is False

    with engine.connect() as connection:
        assert (
            connection.execute(select(func.count()).select_from(decision_snapshot)).scalar_one()
            == 1
        )
        events = connection.execute(
            select(agent_event.c.sequence, agent_event.c.event_type)
            .where(agent_event.c.run_id == run_id)
            .order_by(agent_event.c.sequence)
        ).all()
        assert events[0] == (1, "run.started")
        assert events[-1][1] == "run.completed"
        assert [sequence for sequence, _ in events] == list(range(1, len(events) + 1))
        assert any(event_type == "node.completed" for _, event_type in events)
        correlation_id = connection.execute(
            select(agent_run.c.correlation_id).where(agent_run.c.id == run_id)
        ).scalar_one()
        assert set(
            connection.execute(
                select(agent_event.c.correlation_id).where(agent_event.c.run_id == run_id)
            ).scalars()
        ) == {correlation_id}
        assert (
            connection.execute(
                select(func.count()).select_from(tool_call).where(tool_call.c.run_id == run_id)
            ).scalar_one()
            == 6
        )
        replay = load_events(connection, run_id)
        assert sum(event["type"] == "mcp.tool.completed" for event in replay) == 6
        assert {event["correlation_id"] for event in replay} == {correlation_id}
    engine.dispose()


def test_paper_research_worker_consumes_sip_admission_as_typed_gap(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    run_id = uuid4()
    as_of = datetime(2026, 8, 21, 20, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            insert(agent_run).values(
                id=run_id,
                run_type="RESEARCH",
                idempotency_key=f"paper-research-{run_id}",
                request_hash="9" * 64,
                request_payload={
                    "symbol": "NVDA",
                    "market_data_admission": {
                        "outcome": "ALLOWED_WITH_GAP",
                        "selected_coverage": None,
                        "gap_kind": "UNAVAILABLE",
                        "reason": "SIP entitlement unavailable",
                    },
                },
                symbol="NVDA",
                decision_time=as_of,
                data_cutoff=as_of,
                status="QUEUED",
            )
        )

    assert execute_research_run(
        isolated_database_url,
        str(run_id),
        completed_at=as_of,
        fixture_mode=False,
    )
    with engine.connect() as connection:
        gaps = (
            connection.execute(
                select(evidence_gap).where(evidence_gap.c.reason == "SIP entitlement unavailable")
            )
            .mappings()
            .all()
        )
    assert len(gaps) == 1
    assert gaps[0]["kind"] == "UNAVAILABLE"
    assert gaps[0]["provider"] == "ALPACA"
    engine.dispose()


def test_paper_research_provider_never_falls_back_to_persisted_fixture_news(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    as_of = datetime(2026, 8, 21, 20, tzinfo=UTC)
    with engine.begin() as connection:
        FixtureCatalog.load_default().seed_database(connection)
    provider = PostgresResearchProvider(
        engine,
        coverage=None,
        gap_reason=None,
    )
    response = provider.fetch(FeedType.COMPANY_NEWS, "NVDA", as_of)

    assert response.status is ProviderStatus.NOT_FOUND
    assert response.provider == "ALPACA"
    assert response.records == ()
    assert response.missingness == "MISSING"
    engine.dispose()


def test_paper_research_provider_preserves_persisted_sec_company_facts(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    as_of = datetime(2026, 8, 21, 20, tzinfo=UTC)
    event_time = datetime(2026, 8, 20, 20, tzinfo=UTC)
    available_at = event_time + timedelta(minutes=1)
    raw_id = uuid4()
    fixture_raw_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(raw_data_object),
            [
                {
                    "id": raw_id,
                    "provider": "SEC",
                    "feed_type": FeedType.COMPANY_FACTS.value,
                    "event_time": event_time,
                    "available_at": available_at,
                    "ingested_at": available_at,
                    "content_hash": "e" * 64,
                    "raw_object_key": "test/sec/NVDA/company-facts.json",
                },
                {
                    "id": fixture_raw_id,
                    "provider": "FIXTURE",
                    "feed_type": FeedType.COMPANY_FACTS.value,
                    "event_time": event_time,
                    "available_at": available_at,
                    "ingested_at": available_at,
                    "content_hash": "f" * 64,
                    "raw_object_key": "fixtures/NVDA/company-facts.json",
                },
            ],
        )
        connection.execute(
            insert(normalized_record),
            [
                {
                    "raw_data_object_id": raw_id,
                    "record_type": FeedType.COMPANY_FACTS.value,
                    "record_key": "NVDA:revenue:2026-Q2",
                    "normalization_version": "sec-company-facts-v1",
                    "payload": {"symbol": "NVDA", "revenue": "1000000"},
                },
                {
                    "raw_data_object_id": fixture_raw_id,
                    "record_type": FeedType.COMPANY_FACTS.value,
                    "record_key": "NVDA:fixture-revenue:2026-Q2",
                    "normalization_version": "fixture-v1",
                    "payload": {"symbol": "NVDA", "revenue": "9999999"},
                },
            ],
        )

    response = PostgresResearchProvider(
        engine,
        coverage=None,
        gap_reason=None,
    ).fetch(FeedType.COMPANY_FACTS, "NVDA", as_of)

    assert response.status is ProviderStatus.OK
    assert response.provider == "SEC"
    assert len(response.records) == 1
    assert response.records[0].provider == "SEC"
    assert response.records[0].payload["revenue"] == "1000000"
    engine.dispose()


def test_paper_research_provider_supports_parallel_fetches_with_independent_connections(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    as_of = datetime(2026, 8, 21, 20, tzinfo=UTC)
    provider = PostgresResearchProvider(engine, coverage=None, gap_reason=None)

    with ThreadPoolExecutor(max_workers=5) as executor:
        responses = tuple(
            executor.map(
                lambda feed: provider.fetch(feed, "NVDA", as_of),
                tuple(FeedType),
            )
        )

    assert tuple(response.feed_type for response in responses) == tuple(FeedType)
    engine.dispose()


def test_weekly_worker_runs_real_review_graph_and_is_idempotent(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    research_id = uuid4()
    research_time = datetime(2026, 8, 16, tzinfo=UTC)
    weekly_id = uuid4()
    weekly_time = datetime(2026, 8, 21, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            insert(agent_run),
            [
                {
                    "id": research_id,
                    "run_type": "RESEARCH",
                    "idempotency_key": f"weekly-source-{research_id}",
                    "request_hash": "f" * 64,
                    "request_payload": {"symbol": "NVDA"},
                    "symbol": "NVDA",
                    "decision_time": research_time,
                    "data_cutoff": research_time,
                    "created_at": research_time,
                    "status": "QUEUED",
                },
                {
                    "id": weekly_id,
                    "run_type": "WEEKLY_REVIEW",
                    "idempotency_key": f"weekly-worker-{weekly_id}",
                    "request_hash": "a" * 64,
                    "request_payload": {"scheduled": True},
                    "symbol": None,
                    "decision_time": weekly_time,
                    "data_cutoff": weekly_time,
                    "created_at": weekly_time,
                    "status": "QUEUED",
                },
            ],
        )

    assert (
        execute_research_run(isolated_database_url, str(research_id), completed_at=research_time)
        is True
    )
    assert execute_weekly_review_run(isolated_database_url, str(weekly_id)) is True
    assert execute_weekly_review_run(isolated_database_url, str(weekly_id)) is False

    with engine.connect() as connection:
        assert (
            connection.execute(select(func.count()).select_from(weekly_review_run)).scalar_one()
            == 1
        )
        event_types = (
            connection.execute(
                select(agent_event.c.event_type)
                .where(agent_event.c.run_id == weekly_id)
                .order_by(agent_event.c.sequence)
            )
            .scalars()
            .all()
        )
        assert event_types == ["run.started", *(["node.completed"] * 6), "run.completed"]
    engine.dispose()


def test_paper_weekly_worker_uses_only_persisted_alpaca_prices(
    isolated_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    research_id = uuid4()
    weekly_id = uuid4()
    research_time = datetime(2026, 8, 16, tzinfo=UTC)
    weekly_time = datetime(2026, 8, 21, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            insert(agent_run),
            [
                {
                    "id": research_id,
                    "run_type": "RESEARCH",
                    "idempotency_key": f"paper-weekly-source-{research_id}",
                    "request_hash": "4" * 64,
                    "request_payload": {"symbol": "NVDA"},
                    "symbol": "NVDA",
                    "decision_time": research_time,
                    "data_cutoff": research_time,
                    "created_at": research_time,
                    "status": "QUEUED",
                },
                {
                    "id": weekly_id,
                    "run_type": "WEEKLY_REVIEW",
                    "idempotency_key": f"paper-weekly-{weekly_id}",
                    "request_hash": "5" * 64,
                    "request_payload": {"scheduled": True},
                    "symbol": None,
                    "decision_time": weekly_time,
                    "data_cutoff": weekly_time,
                    "created_at": weekly_time,
                    "status": "QUEUED",
                },
            ],
        )

    assert execute_research_run(
        isolated_database_url,
        str(research_id),
        completed_at=research_time,
    )
    with engine.begin() as connection:
        decision_id = connection.execute(
            select(decision_snapshot.c.id).where(decision_snapshot.c.thesis_id.is_not(None))
        ).scalar_one()
        for index, (event_time, close) in enumerate(
            (
                (datetime(2026, 8, 15, 20, tzinfo=UTC), Decimal("180")),
                (datetime(2026, 8, 17, 20, tzinfo=UTC), Decimal("183")),
                (datetime(2026, 8, 20, 20, tzinfo=UTC), Decimal("186")),
            ),
            start=1,
        ):
            raw_id = uuid4()
            normalized_id = uuid4()
            available_at = event_time + timedelta(minutes=1)
            content_hash = f"{index:064x}"
            raw_object_key = f"test/alpaca/NVDA/{event_time.isoformat()}"
            connection.execute(
                insert(raw_data_object).values(
                    id=raw_id,
                    provider="ALPACA",
                    feed_type=FeedType.PRICE_BARS.value,
                    event_time=event_time,
                    available_at=available_at,
                    ingested_at=available_at,
                    content_hash=content_hash,
                    raw_object_key=raw_object_key,
                )
            )
            connection.execute(
                insert(normalized_record).values(
                    id=normalized_id,
                    raw_data_object_id=raw_id,
                    record_type="market_bar",
                    record_key=f"NVDA:{event_time.isoformat()}",
                    normalization_version="test-alpaca-v1",
                    payload={"close": str(close)},
                )
            )
            connection.execute(
                insert(market_bar).values(
                    id=uuid4(),
                    event_time=event_time,
                    symbol="NVDA",
                    raw_data_object_id=raw_id,
                    normalized_record_id=normalized_id,
                    provider="ALPACA",
                    feed_type=FeedType.PRICE_BARS.value,
                    coverage="IEX",
                    session="REGULAR",
                    content_hash=content_hash,
                    raw_object_key=raw_object_key,
                    available_at=available_at,
                    ingested_at=available_at,
                    close=close,
                    payload={"close": str(close)},
                )
            )
        persisted_prices = _paper_prices(
            connection,
            symbols=("NVDA", "QQQ"),
            cutoff=weekly_time,
        )
        assert [item.event_time for item in persisted_prices["NVDA"]]
        assert any(item.event_time <= research_time for item in persisted_prices["NVDA"])

    def fixture_forbidden() -> FixtureCatalog:
        raise AssertionError("paper weekly review must not load Fixture data")

    monkeypatch.setattr(FixtureCatalog, "load_default", fixture_forbidden)

    assert execute_weekly_review_run(
        isolated_database_url,
        str(weekly_id),
        fixture_mode=False,
    )
    with engine.connect() as connection:
        review = (
            connection.execute(
                select(weekly_review_run).where(weekly_review_run.c.run_key == str(weekly_id))
            )
            .mappings()
            .one()
        )
        assert review["decision_ids"] == [str(decision_id)]
        outcome_count = connection.execute(
            select(func.count()).select_from(decision_outcome)
        ).scalar_one()
        assert outcome_count == 1
    engine.dispose()


def test_portfolio_worker_uses_singleton_capital_without_forcing_abstain_order(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    research_id = uuid4()
    research_time = datetime(2026, 8, 16, tzinfo=UTC)
    portfolio_id = uuid4()
    portfolio_time = datetime(2026, 8, 21, 20, 30, tzinfo=UTC)
    context_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(agent_run),
            [
                {
                    "id": research_id,
                    "run_type": "RESEARCH",
                    "idempotency_key": f"portfolio-source-{research_id}",
                    "request_hash": "b" * 64,
                    "request_payload": {"symbol": "NVDA"},
                    "symbol": "NVDA",
                    "decision_time": research_time,
                    "data_cutoff": research_time,
                    "created_at": research_time,
                    "status": "QUEUED",
                },
                {
                    "id": portfolio_id,
                    "run_type": "PORTFOLIO",
                    "idempotency_key": f"portfolio-worker-{portfolio_id}",
                    "request_hash": "c" * 64,
                    "request_payload": {"scheduled": True},
                    "symbol": None,
                    "decision_time": portfolio_time,
                    "data_cutoff": portfolio_time,
                    "created_at": portfolio_time,
                    "status": "QUEUED",
                },
            ],
        )
    assert (
        execute_research_run(isolated_database_url, str(research_id), completed_at=research_time)
        is True
    )
    with pytest.raises(RuntimeError, match="market context"):
        execute_portfolio_run(isolated_database_url, str(portfolio_id))
    with engine.begin() as connection:
        assert (
            connection.execute(
                select(agent_run.c.status).where(agent_run.c.id == portfolio_id)
            ).scalar_one()
            == "QUEUED"
        )
        connection.execute(
            insert(market_context_snapshot).values(
                id=context_id,
                as_of=portfolio_time,
                available_at=portfolio_time,
                qqq_trend=Decimal("0.01"),
                qqq_volatility=Decimal("0.18"),
                soxx_relative_strength=Decimal("0.01"),
                vix=Decimal("18"),
                regime_label="RISK_ON",
                algorithm_version="fixture-context-v1",
                source_lineage=[str(uuid4())],
            )
        )
    assert execute_portfolio_run(isolated_database_url, str(portfolio_id)) is True
    assert execute_portfolio_run(isolated_database_url, str(portfolio_id)) is False

    with engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(risk_decision)).scalar_one() == 0
        assert connection.execute(
            select(func.sum(cash_ledger.c.debit)).where(cash_ledger.c.account == "ASSET:CASH")
        ).scalar_one() == Decimal("100000")
        event_types = (
            connection.execute(
                select(agent_event.c.event_type)
                .where(agent_event.c.run_id == portfolio_id)
                .order_by(agent_event.c.sequence)
            )
            .scalars()
            .all()
        )
        assert event_types == [
            "run.started",
            "run.retry_scheduled",
            "run.started",
            *(["node.completed"] * 7),
            "run.completed",
        ]
    engine.dispose()


def test_portfolio_and_weekly_workers_exclude_decisions_not_yet_available(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    research_id = uuid4()
    portfolio_id = uuid4()
    weekly_id = uuid4()
    research_time = datetime(2026, 8, 16, tzinfo=UTC)
    cutoff = datetime(2026, 8, 21, 20, 30, tzinfo=UTC)
    future_availability = datetime(2026, 8, 22, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            insert(agent_run),
            [
                {
                    "id": research_id,
                    "run_type": "RESEARCH",
                    "idempotency_key": f"future-source-{research_id}",
                    "request_hash": "1" * 64,
                    "request_payload": {"symbol": "NVDA"},
                    "symbol": "NVDA",
                    "decision_time": research_time,
                    "data_cutoff": research_time,
                    "created_at": research_time,
                    "status": "QUEUED",
                },
                {
                    "id": portfolio_id,
                    "run_type": "PORTFOLIO",
                    "idempotency_key": f"future-portfolio-{portfolio_id}",
                    "request_hash": "2" * 64,
                    "request_payload": {"scheduled": True},
                    "symbol": None,
                    "decision_time": cutoff,
                    "data_cutoff": cutoff,
                    "created_at": cutoff,
                    "status": "QUEUED",
                },
                {
                    "id": weekly_id,
                    "run_type": "WEEKLY_REVIEW",
                    "idempotency_key": f"future-weekly-{weekly_id}",
                    "request_hash": "3" * 64,
                    "request_payload": {"scheduled": True},
                    "symbol": None,
                    "decision_time": cutoff,
                    "data_cutoff": cutoff,
                    "created_at": cutoff,
                    "status": "QUEUED",
                },
            ],
        )
        connection.execute(
            insert(market_context_snapshot).values(
                as_of=cutoff,
                available_at=cutoff,
                qqq_trend=Decimal("0.01"),
                qqq_volatility=Decimal("0.18"),
                soxx_relative_strength=Decimal("0.01"),
                vix=Decimal("18"),
                regime_label="RISK_ON",
                algorithm_version="fixture-context-v1",
                source_lineage=[str(uuid4())],
            )
        )

    assert (
        execute_research_run(
            isolated_database_url, str(research_id), completed_at=future_availability
        )
        is True
    )
    with pytest.raises(RuntimeError, match="frozen research decision"):
        execute_portfolio_run(isolated_database_url, str(portfolio_id))
    with engine.connect() as connection:
        assert (
            connection.execute(
                select(agent_run.c.status).where(agent_run.c.id == portfolio_id)
            ).scalar_one()
            == "QUEUED"
        )
    assert execute_weekly_review_run(isolated_database_url, str(weekly_id)) is True
    with engine.connect() as connection:
        assert (
            connection.execute(select(decision_snapshot.c.available_at)).scalar_one()
            == future_availability
        )
        assert (
            connection.execute(
                select(weekly_review_run.c.decision_ids).where(
                    weekly_review_run.c.run_key == str(weekly_id)
                )
            ).scalar_one()
            == []
        )
    engine.dispose()


def test_weekly_worker_excludes_append_only_superseded_research_decision(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    contaminated_run_id = uuid4()
    corrected_run_id = uuid4()
    weekly_id = uuid4()
    contaminated_time = datetime(2026, 8, 16, 20, 15, tzinfo=UTC)
    corrected_time = datetime(2026, 8, 16, 20, 16, tzinfo=UTC)
    # The replacement fact is persisted during this test, so the review cutoff must
    # be after its actual database creation time as well as its historical data cutoff.
    cutoff = datetime.now(UTC) + timedelta(minutes=1)
    with engine.begin() as connection:
        connection.execute(
            insert(agent_run),
            [
                {
                    "id": contaminated_run_id,
                    "run_type": "RESEARCH",
                    "idempotency_key": f"superseded-source-{contaminated_run_id}",
                    "request_hash": "4" * 64,
                    "request_payload": {"symbol": "NVDA"},
                    "symbol": "NVDA",
                    "decision_time": contaminated_time,
                    "data_cutoff": contaminated_time,
                    "created_at": contaminated_time,
                    "status": "QUEUED",
                },
                {
                    "id": corrected_run_id,
                    "run_type": "RESEARCH",
                    "idempotency_key": f"corrected-source-{corrected_run_id}",
                    "request_hash": "5" * 64,
                    "request_payload": {"symbol": "NVDA"},
                    "symbol": "NVDA",
                    "decision_time": corrected_time,
                    "data_cutoff": corrected_time,
                    "created_at": corrected_time,
                    "status": "QUEUED",
                },
                {
                    "id": weekly_id,
                    "run_type": "WEEKLY_REVIEW",
                    "idempotency_key": f"superseded-weekly-{weekly_id}",
                    "request_hash": "6" * 64,
                    "request_payload": {"scheduled": True},
                    "symbol": None,
                    "decision_time": cutoff,
                    "data_cutoff": cutoff,
                    "created_at": cutoff,
                    "status": "QUEUED",
                },
            ],
        )

    assert execute_research_run(
        isolated_database_url, str(contaminated_run_id), completed_at=contaminated_time
    )
    assert execute_research_run(
        isolated_database_url, str(corrected_run_id), completed_at=corrected_time
    )
    with engine.begin() as connection:
        contaminated_decision_id = connection.execute(
            select(decision_snapshot.c.id)
            .join(investment_thesis, decision_snapshot.c.thesis_id == investment_thesis.c.id)
            .where(investment_thesis.c.run_id == contaminated_run_id)
        ).scalar_one()
        corrected_decision_id = connection.execute(
            select(decision_snapshot.c.id)
            .join(investment_thesis, decision_snapshot.c.thesis_id == investment_thesis.c.id)
            .where(investment_thesis.c.run_id == corrected_run_id)
        ).scalar_one()
        connection.execute(
            insert(decision_diff).values(
                decision_id=corrected_decision_id,
                previous_decision_id=contaminated_decision_id,
                generator="DETERMINISTIC_CODE",
                changes={"provenance": {"before": "FIXTURE", "after": "ALPACA"}},
                created_at=corrected_time,
            )
        )

    assert execute_weekly_review_run(isolated_database_url, str(weekly_id))
    with engine.connect() as connection:
        assert connection.execute(
            select(weekly_review_run.c.decision_ids).where(
                weekly_review_run.c.run_key == str(weekly_id)
            )
        ).scalar_one() == [str(corrected_decision_id)]
    engine.dispose()


def test_market_monitor_records_durable_scan_and_rejects_redelivery(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    run_id = uuid4()
    cutoff = datetime(2026, 8, 21, 15, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            insert(agent_run).values(
                id=run_id,
                run_type="ALERT_MONITOR",
                idempotency_key=f"monitor-worker-{run_id}",
                request_hash="9" * 64,
                request_payload={"scheduled": True},
                decision_time=cutoff,
                data_cutoff=cutoff,
                status="QUEUED",
            )
        )

    assert execute_market_monitor_run(isolated_database_url, str(run_id)) is True
    assert execute_market_monitor_run(isolated_database_url, str(run_id)) is False
    with engine.connect() as connection:
        events = connection.execute(
            select(agent_event.c.event_type, agent_event.c.payload)
            .where(agent_event.c.run_id == run_id)
            .order_by(agent_event.c.sequence)
        ).all()
        assert [event_type for event_type, _ in events] == [
            "run.started",
            "monitor.completed",
            "run.completed",
        ]
        assert events[1].payload == {"visible_bars": 0}
    engine.dispose()
