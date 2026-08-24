from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import TYPE_CHECKING, Literal, Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

from celery.schedules import crontab  # type: ignore[import-untyped]
from sqlalchemy import Connection, create_engine, select, update

from stock_platform.application.ingestion.jobs import IngestionJobSpec
from stock_platform.application.market_data.policy import (
    EntitlementSnapshot,
    MarketDataDecision,
    PolicyOutcome,
    route_market_data,
)
from stock_platform.application.runs import (
    RunAdmissionLimit,
    RunType,
    admit_run,
    append_run_event,
)
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.ingestion.models import (
    DataPurpose,
    FeedType,
    IngestionRequest,
    MarketDataCoverage,
    MarketSession,
)
from stock_platform.infrastructure.db.models.tables import agent_run, watchlist_item
from stock_platform.infrastructure.observability.metrics import platform_metrics
from stock_platform.settings import Settings

if TYPE_CHECKING:
    from stock_platform.workers.ingestion_tasks import BarTimeframe

Dispatch = Callable[[str, str], None]


class BackfillJobStore(Protocol):
    def enqueue(self, spec: IngestionJobSpec, *, now: datetime) -> UUID: ...


@dataclass(frozen=True, slots=True)
class ScheduledAlpacaBackfill:
    decision: MarketDataDecision
    job_ids: tuple[UUID, ...]


NEW_YORK = ZoneInfo("America/New_York")
TASKS = {
    "RESEARCH": "stock_platform.workers.research_tasks.run_research",
    "ALERT_MONITOR": "stock_platform.workers.research_tasks.monitor_market",
    "PORTFOLIO": "stock_platform.workers.portfolio_tasks.run_portfolio",
    "WEEKLY_REVIEW": "stock_platform.workers.review_tasks.run_weekly_review",
}

beat_schedule = {
    "daily-research-after-close": {
        "task": "stock_platform.workers.schedules.daily_research",
        "schedule": crontab(minute=15, hour="20,21", day_of_week="1-5"),
    },
    "intraday-market-monitor": {
        "task": "stock_platform.workers.schedules.intraday_monitor",
        "schedule": crontab(minute="*", hour="13-21", day_of_week="1-5"),
    },
    "portfolio-fixed-cutoff": {
        "task": "stock_platform.workers.schedules.portfolio_decision",
        "schedule": crontab(minute=30, hour="20,21", day_of_week="1-5"),
    },
    "weekly-review-after-maturity": {
        "task": "stock_platform.workers.schedules.weekly_review",
        "schedule": crontab(minute=0, hour=13, day_of_week="1"),
    },
    "recover-queued-runs": {
        "task": "stock_platform.workers.schedules.recover_queued",
        "schedule": 60.0,
    },
}


def is_market_session(value: datetime, *, closures: Collection[date] = ()) -> bool:
    local = require_aware(value).astimezone(NEW_YORK)
    return (
        local.weekday() < 5
        and local.date() not in closures
        and time(9, 30) <= local.time().replace(tzinfo=None) < time(16)
    )


def is_market_cutoff(value: datetime, cutoff: time, *, closures: Collection[date] = ()) -> bool:
    local = require_aware(value).astimezone(NEW_YORK)
    return (
        local.weekday() < 5
        and local.date() not in closures
        and local.time().replace(tzinfo=None) == cutoff
    )


def schedule_key(kind: str, cutoff: datetime, *, symbol: str | None = None) -> str:
    aware = require_aware(cutoff).astimezone(UTC)
    prefix = f"{kind}:{Symbol(symbol)}" if symbol is not None else kind
    return f"{prefix}:{aware.isoformat()}"


def schedule_alpaca_backfills(
    store: BackfillJobStore,
    *,
    symbol: str,
    dataset: FeedType,
    timeframe: BarTimeframe | None,
    start: datetime,
    end: datetime,
    purpose: DataPurpose,
    required_coverage: MarketDataCoverage,
    session: MarketSession,
    entitlement: EntitlementSnapshot,
    now: datetime,
    max_jobs: int = 24,
) -> ScheduledAlpacaBackfill:
    from stock_platform.workers.ingestion_tasks import plan_alpaca_backfill

    if max_jobs < 1:
        raise ValueError("max_jobs must be positive")
    decision = route_market_data(
        purpose=purpose,
        required_coverage=required_coverage,
        session=session,
        entitlement=entitlement,
    )
    if decision.outcome is PolicyOutcome.DENIED_NO_ACTION:
        return ScheduledAlpacaBackfill(decision=decision, job_ids=())
    slices = plan_alpaca_backfill(
        dataset=dataset,
        timeframe=timeframe,
        start=start,
        end=end,
    )
    if len(slices) > max_jobs:
        raise ValueError("backfill plan exceeds bounded job count")
    queued_at = require_aware(now).astimezone(UTC)
    job_ids: list[UUID] = []
    for item in slices:
        request = IngestionRequest(
            {
                "symbol": str(Symbol(symbol)),
                "timeframe": item.timeframe.value if item.timeframe is not None else None,
                "coverage": (
                    decision.selected_coverage.value
                    if decision.selected_coverage is not None
                    else None
                ),
                "session": session.value,
                "priority": item.priority.value,
                "page_token": item.page_token,
                "entitlement": {
                    "version": entitlement.version,
                    "observed_at": entitlement.observed_at,
                    "coverage": sorted(value.value for value in entitlement.coverage),
                    "overnight": entitlement.overnight,
                    "sip_delay_seconds": (
                        int(entitlement.sip_delay.total_seconds())
                        if entitlement.sip_delay is not None
                        else None
                    ),
                },
                "gap_kind": decision.gap_kind,
                "gap_reason": decision.reason,
            }
        )
        job_ids.append(
            store.enqueue(
                IngestionJobSpec(
                    request=request,
                    provider="ALPACA",
                    dataset=dataset,
                    window_start=item.start,
                    window_end=item.end,
                    purpose=purpose,
                    policy_version=entitlement.version,
                    max_attempts=3,
                ),
                now=queued_at,
            )
        )
    return ScheduledAlpacaBackfill(decision=decision, job_ids=tuple(job_ids))


def _dispatch(task: str, run_id: str) -> None:
    from stock_platform.workers.celery_app import celery_app

    celery_app.send_task(task, args=[run_id], task_id=run_id)


def _schedule(
    connection: Connection,
    settings: Settings,
    cutoff: datetime,
    *,
    kind: str,
    run_type: RunType,
    symbol: str | None = None,
    dispatch: Dispatch = _dispatch,
) -> str | None:
    payload = {
        "symbol": symbol,
        "decision_time": cutoff.isoformat(),
        "data_cutoff": cutoff.isoformat(),
        "scheduled": True,
    }
    try:
        admitted = admit_run(
            connection,
            max_active_runs=settings.max_active_agent_runs,
            run_type=run_type,
            idempotency_key=schedule_key(kind, cutoff, symbol=symbol),
            payload=payload,
            symbol=symbol,
            decision_time=cutoff,
            data_cutoff=cutoff,
        )
    except RunAdmissionLimit:
        return None
    run_id = str(admitted.id)
    if not admitted.replayed:
        dispatch(TASKS[run_type], run_id)
    return run_id


def schedule_daily_research(
    connection: Connection,
    settings: Settings,
    cutoff: datetime,
    *,
    closures: Collection[date] = (),
    dispatch: Dispatch = _dispatch,
) -> tuple[str, ...]:
    if not is_market_cutoff(cutoff, time(16, 15), closures=closures):
        return ()
    symbols = connection.execute(
        select(watchlist_item.c.symbol)
        .where(watchlist_item.c.daily_research.is_(True))
        .order_by(watchlist_item.c.symbol)
    ).scalars()
    return tuple(
        run_id
        for symbol in symbols
        if (
            run_id := _schedule(
                connection,
                settings,
                cutoff,
                kind="daily-research",
                run_type="RESEARCH",
                symbol=symbol,
                dispatch=dispatch,
            )
        )
        is not None
    )


def schedule_intraday_monitor(
    connection: Connection,
    settings: Settings,
    cutoff: datetime,
    *,
    closures: Collection[date] = (),
    dispatch: Dispatch = _dispatch,
) -> str | None:
    if not is_market_session(cutoff, closures=closures):
        return None
    return _schedule(
        connection,
        settings,
        cutoff,
        kind="intraday-monitor",
        run_type="ALERT_MONITOR",
        dispatch=dispatch,
    )


def schedule_portfolio_decision(
    connection: Connection,
    settings: Settings,
    cutoff: datetime,
    *,
    closures: Collection[date] = (),
    dispatch: Dispatch = _dispatch,
) -> str | None:
    if not is_market_cutoff(cutoff, time(16, 30), closures=closures):
        return None
    return _schedule(
        connection,
        settings,
        cutoff,
        kind="portfolio",
        run_type="PORTFOLIO",
        dispatch=dispatch,
    )


def schedule_weekly_review(
    connection: Connection,
    settings: Settings,
    cutoff: datetime,
    *,
    dispatch: Dispatch = _dispatch,
) -> str | None:
    return _schedule(
        connection,
        settings,
        cutoff,
        kind="weekly-review",
        run_type="WEEKLY_REVIEW",
        dispatch=dispatch,
    )


def recover_queued_runs(
    connection: Connection,
    *,
    now: datetime | None = None,
    dispatch: Dispatch = _dispatch,
) -> tuple[str, ...]:
    recovery_time = require_aware(now or datetime.now(UTC))
    exhausted = connection.execute(
        update(agent_run)
        .where(
            agent_run.c.status == "RUNNING",
            agent_run.c.lease_expires_at <= recovery_time,
            agent_run.c.attempt_count >= agent_run.c.max_attempts,
        )
        .values(
            status="FAILED",
            lease_expires_at=None,
            last_error={"type": "WorkerLost", "message": "worker lease expired"},
            updated_at=recovery_time,
        )
        .returning(agent_run.c.id)
    ).scalars()
    for run_id in exhausted:
        append_run_event(
            connection,
            run_id,
            "run.failed",
            {"status": "FAILED", "reason": "worker lease expired"},
        )
    connection.execute(
        update(agent_run)
        .where(
            agent_run.c.status == "RUNNING",
            agent_run.c.lease_expires_at <= recovery_time,
            agent_run.c.attempt_count < agent_run.c.max_attempts,
        )
        .values(status="QUEUED", lease_expires_at=None, updated_at=recovery_time)
    )
    rows = connection.execute(
        select(agent_run.c.id, agent_run.c.run_type)
        .where(
            agent_run.c.status == "QUEUED",
            agent_run.c.attempt_count < agent_run.c.max_attempts,
        )
        .order_by(agent_run.c.created_at)
    ).all()
    platform_metrics.set_queue(queue="agent-runs", depth=len(rows))
    for run_id, run_type in rows:
        dispatch(TASKS[run_type], str(run_id))
    return tuple(str(run_id) for run_id, _ in rows)


def _run_schedule(kind: Literal["research", "intraday", "portfolio", "review", "recover"]) -> None:
    settings = Settings()
    with create_engine(settings.database_url).begin() as connection:
        now = datetime.now(UTC).replace(second=0, microsecond=0)
        if kind == "research":
            schedule_daily_research(connection, settings, now)
        elif kind == "intraday":
            schedule_intraday_monitor(connection, settings, now)
        elif kind == "portfolio":
            schedule_portfolio_decision(connection, settings, now)
        elif kind == "review":
            schedule_weekly_review(connection, settings, now)
        else:
            recover_queued_runs(connection)


from stock_platform.workers.celery_app import celery_app  # noqa: E402, I001


@celery_app.task(name="stock_platform.workers.schedules.daily_research")  # type: ignore[untyped-decorator]
def daily_research() -> None:
    _run_schedule("research")


@celery_app.task(name="stock_platform.workers.schedules.intraday_monitor")  # type: ignore[untyped-decorator]
def intraday_monitor() -> None:
    _run_schedule("intraday")


@celery_app.task(name="stock_platform.workers.schedules.portfolio_decision")  # type: ignore[untyped-decorator]
def portfolio_decision() -> None:
    _run_schedule("portfolio")


@celery_app.task(name="stock_platform.workers.schedules.weekly_review")  # type: ignore[untyped-decorator]
def weekly_review() -> None:
    _run_schedule("review")


@celery_app.task(name="stock_platform.workers.schedules.recover_queued")  # type: ignore[untyped-decorator]
def recover_queued() -> None:
    _run_schedule("recover")
