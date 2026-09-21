from datetime import UTC, datetime
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, insert, select, update
from stock_platform.infrastructure.db.models.tables import (
    agent_event,
    agent_run,
    security,
    watchlist_item,
)
from stock_platform.settings import Settings
from stock_platform.workers.schedules import (
    recover_queued_runs,
    replace_exhausted_run,
    requeue_failed_run,
    schedule_agent_catch_up,
    schedule_daily_research,
    schedule_intraday_monitor,
    schedule_portfolio_decision,
    schedule_weekly_review,
)


def test_failed_run_requires_explicit_audited_retry(isolated_database_url: str) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database_url)
    run_id = uuid4()
    cutoff = datetime(2026, 9, 18, 20, 15, tzinfo=UTC)
    dispatched: list[tuple[str, str]] = []
    with engine.begin() as connection:
        connection.execute(
            insert(agent_run).values(
                id=run_id,
                run_type="RESEARCH",
                idempotency_key=f"failed-research-{run_id}",
                request_hash="f" * 64,
                request_payload={"symbol": "NVDA"},
                symbol="NVDA",
                decision_time=cutoff,
                data_cutoff=cutoff,
                status="FAILED",
                attempt_count=1,
                max_attempts=3,
                last_error={"type": "MultipleResultsFound", "message": "worker failed"},
            )
        )

        assert requeue_failed_run(
            connection,
            run_id,
            dispatch=lambda task, value: dispatched.append((task, value)),
        )
        assert not requeue_failed_run(
            connection,
            run_id,
            dispatch=lambda task, value: dispatched.append((task, value)),
        )
        row = connection.execute(select(agent_run).where(agent_run.c.id == run_id)).mappings().one()
        events = connection.execute(
            select(agent_event.c.event_type, agent_event.c.payload).where(
                agent_event.c.run_id == run_id
            )
        ).all()

    assert row["status"] == "QUEUED"
    assert row["last_error"] == {"type": "MultipleResultsFound", "message": "worker failed"}
    assert events == [("run.operator_retry_queued", {"previous_attempt": 1})]
    assert dispatched == [("stock_platform.workers.research_tasks.run_research", str(run_id))]
    engine.dispose()


def test_exhausted_run_requires_one_pinned_audited_replacement(
    isolated_database_url: str,
) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database_url)
    original_id = uuid4()
    cutoff = datetime(2026, 9, 18, 20, 15, tzinfo=UTC)
    settings = Settings(
        environment="test", database_url=isolated_database_url, max_active_agent_runs=20
    )
    dispatched: list[tuple[str, str]] = []
    with engine.begin() as connection:
        connection.execute(
            insert(agent_run).values(
                id=original_id,
                run_type="RESEARCH",
                idempotency_key=f"failed-research-{original_id}",
                request_hash="e" * 64,
                request_payload={"symbol": "NVDA", "scheduled": True},
                symbol="NVDA",
                decision_time=cutoff,
                data_cutoff=cutoff,
                status="FAILED",
                attempt_count=3,
                max_attempts=3,
                research_scoring_policy_version="research-frozen",
                risk_policy_version="risk-frozen",
                execution_policy_version="execution-frozen",
                confidence_policy_version="confidence-frozen",
                prompt_version="prompt-frozen",
                model_version="model-frozen",
                last_error={"type": "NoResultFound", "message": "worker failed"},
            )
        )

        replacement_id = replace_exhausted_run(
            connection,
            settings,
            original_id,
            dispatch=lambda task, value: dispatched.append((task, value)),
        )
        replay_id = replace_exhausted_run(
            connection,
            settings,
            original_id,
            dispatch=lambda task, value: dispatched.append((task, value)),
        )
        assert replacement_id is not None
        assert replay_id == replacement_id
        replacement = (
            connection.execute(select(agent_run).where(agent_run.c.id == replacement_id))
            .mappings()
            .one()
        )
        original_events = connection.execute(
            select(agent_event.c.event_type, agent_event.c.payload).where(
                agent_event.c.run_id == original_id
            )
        ).all()
        replacement_events = connection.execute(
            select(agent_event.c.event_type, agent_event.c.payload).where(
                agent_event.c.run_id == replacement_id
            )
        ).all()

    assert replacement["status"] == "QUEUED"
    assert replacement["request_payload"]["replaces_failed_run_id"] == str(original_id)
    assert (
        replacement["research_scoring_policy_version"],
        replacement["risk_policy_version"],
        replacement["execution_policy_version"],
        replacement["confidence_policy_version"],
        replacement["prompt_version"],
        replacement["model_version"],
    ) == (
        "research-frozen",
        "risk-frozen",
        "execution-frozen",
        "confidence-frozen",
        "prompt-frozen",
        "model-frozen",
    )
    assert original_events == [
        ("run.replacement_queued", {"replacement_run_id": str(replacement_id)})
    ]
    assert replacement_events == [
        ("run.replaces_failed", {"failed_run_id": str(original_id)})
    ]
    assert dispatched == [
        ("stock_platform.workers.research_tasks.run_research", str(replacement_id))
    ]
    engine.dispose()


def test_agent_catch_up_reuses_latest_closed_session_runs(
    isolated_database_url: str,
) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database_url)
    settings = Settings(
        environment="test", database_url=isolated_database_url, max_active_agent_runs=20
    )
    dispatched: list[tuple[str, str]] = []
    startup = datetime(2026, 9, 19, 12, tzinfo=UTC)

    with engine.begin() as connection:
        security_id = uuid4()
        connection.execute(insert(security).values(id=security_id, instrument_type="EQUITY"))
        connection.execute(insert(watchlist_item).values(security_id=security_id, symbol="NVDA"))

        first = schedule_agent_catch_up(
            connection,
            settings,
            now=startup,
            dispatch=lambda task, run_id: dispatched.append((task, run_id)),
        )
        replay = schedule_agent_catch_up(
            connection,
            settings,
            now=startup,
            dispatch=lambda task, run_id: dispatched.append((task, run_id)),
        )

        assert replay == first
        assert first.research_cutoff == datetime(2026, 9, 18, 20, 15, tzinfo=UTC)
        assert first.portfolio_cutoff == datetime(2026, 9, 18, 20, 30, tzinfo=UTC)
        assert len(first.research_run_ids) == 1
        assert first.portfolio_run_id is not None
        assert connection.execute(select(func.count()).select_from(agent_run)).scalar_one() == 2
        assert len(dispatched) == 2

    engine.dispose()


def test_scheduled_runs_are_durable_idempotent_and_recoverable(
    isolated_database_url: str,
) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database_url)
    dispatched: list[tuple[str, str]] = []

    def dispatch(task: str, run_id: str) -> None:
        dispatched.append((task, run_id))

    settings = Settings(
        environment="test", database_url=isolated_database_url, max_active_agent_runs=20
    )
    cutoff = datetime(2026, 8, 17, 20, 15, tzinfo=UTC)
    portfolio_cutoff = datetime(2026, 8, 17, 20, 30, tzinfo=UTC)

    with engine.begin() as connection:
        nvda_id = uuid4()
        msft_id = uuid4()
        connection.execute(
            insert(security),
            [
                {"id": nvda_id, "instrument_type": "COMMON_STOCK"},
                {"id": msft_id, "instrument_type": "COMMON_STOCK"},
            ],
        )
        connection.execute(
            insert(watchlist_item),
            [
                {"security_id": nvda_id, "symbol": "NVDA"},
                {"security_id": msft_id, "symbol": "MSFT"},
            ],
        )
        first = schedule_daily_research(connection, settings, cutoff, dispatch=dispatch)
        replay = schedule_daily_research(connection, settings, cutoff, dispatch=dispatch)
        too_early = schedule_portfolio_decision(connection, settings, cutoff, dispatch=dispatch)
        portfolio = schedule_portfolio_decision(
            connection, settings, portfolio_cutoff, dispatch=dispatch
        )
        review = schedule_weekly_review(connection, settings, cutoff, dispatch=dispatch)
        intraday = schedule_intraday_monitor(
            connection, settings, datetime(2026, 8, 17, 15, tzinfo=UTC), dispatch=dispatch
        )
        closed = schedule_intraday_monitor(
            connection,
            settings,
            datetime(2026, 8, 16, 15, tzinfo=UTC),
            dispatch=dispatch,
        )

        assert first == replay
        assert len(first) == 2
        assert too_early is None
        assert portfolio is not None
        assert review is not None
        assert intraday is not None
        assert closed is None
        assert connection.execute(select(func.count()).select_from(agent_run)).scalar_one() == 5
        assert len(dispatched) == 5

        dispatched.clear()
        recovered = recover_queued_runs(connection, dispatch=dispatch)
        assert len(recovered) == 5
        assert len(dispatched) == 5

        expired_id = first[0]
        connection.execute(
            update(agent_run)
            .where(agent_run.c.id == expired_id)
            .values(
                status="RUNNING",
                lease_expires_at=datetime(2026, 8, 17, 20, 14, tzinfo=UTC),
            )
        )
        dispatched.clear()
        recovered = recover_queued_runs(
            connection,
            now=datetime(2026, 8, 17, 20, 16, tzinfo=UTC),
            dispatch=dispatch,
        )
        assert expired_id in recovered
        assert (
            connection.execute(
                select(agent_run.c.status).where(agent_run.c.id == expired_id)
            ).scalar_one()
            == "QUEUED"
        )

        connection.execute(
            update(agent_run)
            .where(agent_run.c.id == expired_id)
            .values(
                status="RUNNING",
                attempt_count=3,
                lease_expires_at=datetime(2026, 8, 17, 20, 14, tzinfo=UTC),
            )
        )
        dispatched.clear()
        recover_queued_runs(
            connection,
            now=datetime(2026, 8, 17, 20, 16, tzinfo=UTC),
            dispatch=dispatch,
        )
        exhausted = connection.execute(
            select(agent_run.c.status, agent_run.c.last_error).where(agent_run.c.id == expired_id)
        ).one()
        assert exhausted.status == "FAILED"
        assert exhausted.last_error == {
            "type": "WorkerLost",
            "message": "worker lease expired",
        }
        assert all(run_id != expired_id for _, run_id in dispatched)

    engine.dispose()


def test_paper_run_admission_records_research_gap_and_denies_portfolio_without_sip(
    isolated_database_url: str,
) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database_url)
    settings = Settings(
        environment="paper",
        database_url=isolated_database_url,
        max_active_agent_runs=20,
        alpaca_data_key="test-key",
        alpaca_data_secret="test-secret",
        alpaca_entitlement_coverage="IEX",
        alpaca_entitlement_version="operator-verified-v1",
    )
    research_cutoff = datetime(2026, 8, 17, 20, 15, tzinfo=UTC)
    portfolio_cutoff = datetime(2026, 8, 17, 20, 30, tzinfo=UTC)
    with engine.begin() as connection:
        security_id = uuid4()
        connection.execute(insert(security).values(id=security_id, instrument_type="EQUITY"))
        connection.execute(insert(watchlist_item).values(security_id=security_id, symbol="NVDA"))

        research_ids = schedule_daily_research(
            connection,
            settings,
            research_cutoff,
            dispatch=lambda _task, _run_id: None,
        )
        portfolio_id = schedule_portfolio_decision(
            connection,
            settings,
            portfolio_cutoff,
            dispatch=lambda _task, _run_id: None,
        )
        payload = connection.execute(
            select(agent_run.c.request_payload).where(agent_run.c.id == research_ids[0])
        ).scalar_one()

    assert payload["market_data_admission"] == {
        "outcome": "ALLOWED_WITH_GAP",
        "selected_coverage": "IEX",
        "gap_kind": "UNAVAILABLE",
        "reason": "SIP entitlement unavailable",
        "entitlement_version": "operator-verified-v1",
        "declared_delay_seconds": None,
    }
    assert portfolio_id is None
    engine.dispose()
