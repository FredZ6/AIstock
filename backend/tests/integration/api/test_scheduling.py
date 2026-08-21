from datetime import UTC, datetime

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, insert, select, update
from stock_platform.infrastructure.db.models.tables import agent_run, watchlist_item
from stock_platform.settings import Settings
from stock_platform.workers.schedules import (
    recover_queued_runs,
    schedule_daily_research,
    schedule_intraday_monitor,
    schedule_portfolio_decision,
    schedule_weekly_review,
)


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
        connection.execute(insert(watchlist_item), [{"symbol": "NVDA"}, {"symbol": "MSFT"}])
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
