from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, time, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from stock_platform.application.ingestion.jobs import IngestionJobAdmission, IngestionJobSpec
from stock_platform.application.market_data.policy import (
    EntitlementSnapshot,
    MarketCalendar,
)
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.ingestion.models import (
    DataPurpose,
    FeedType,
    MarketDataCoverage,
    MarketSession,
)

if TYPE_CHECKING:
    from stock_platform.workers.ingestion_tasks import BarTimeframe

ALPACA_INGESTION_TASK = "stock_platform.workers.ingestion_tasks.run_alpaca_ingestion_job"
ALPACA_INGESTION_QUEUE = "ingestion-low"


class BackfillJobStore(Protocol):
    def enqueue_with_result(
        self, spec: IngestionJobSpec, *, now: datetime
    ) -> IngestionJobAdmission: ...


QueuedJobEligibility = Callable[[UUID], bool]
RefreshPublisher = Callable[[str, UUID, str], None]


class WatchlistRefreshStatus(StrEnum):
    QUEUED = "queued"
    ALREADY_QUEUED = "already_queued"
    NO_SYMBOLS = "no_symbols"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class WatchlistRefreshResult:
    status: WatchlistRefreshStatus
    job_ids: tuple[UUID, ...]
    symbol_count: int
    requested_at: datetime
    data_cutoff: datetime | None
    timeframe: BarTimeframe | None
    feed: MarketDataCoverage | None
    message: str


def request_watchlist_market_data_refresh(
    *,
    store: BackfillJobStore,
    symbols: Iterable[str],
    entitlement: EntitlementSnapshot | None,
    now: datetime,
    is_queued: QueuedJobEligibility,
    publish: RefreshPublisher,
) -> WatchlistRefreshResult:
    """Admit a bounded latest-bar request and publish eligible durable jobs."""
    from stock_platform.workers.ingestion_tasks import BarTimeframe
    from stock_platform.workers.schedules import (
        latest_completed_market_cutoff,
        schedule_alpaca_backfills,
    )

    requested_at = require_aware(now).astimezone(UTC)
    normalized_symbols = tuple(str(Symbol(symbol.strip())) for symbol in symbols)
    if (
        entitlement is None
        or entitlement.provider.upper() != "ALPACA"
        or MarketDataCoverage.IEX not in entitlement.coverage
    ):
        return WatchlistRefreshResult(
            status=WatchlistRefreshStatus.UNAVAILABLE,
            job_ids=(),
            symbol_count=len(normalized_symbols),
            requested_at=requested_at,
            data_cutoff=None,
            timeframe=None,
            feed=None,
            message="Alpaca IEX entitlement is unavailable.",
        )

    feed = MarketDataCoverage.IEX
    if not normalized_symbols:
        return WatchlistRefreshResult(
            status=WatchlistRefreshStatus.NO_SYMBOLS,
            job_ids=(),
            symbol_count=0,
            requested_at=requested_at,
            data_cutoff=None,
            timeframe=None,
            feed=feed,
            message="No monitored Watchlist symbols are available.",
        )

    minute_cutoff = requested_at.replace(second=0, microsecond=0)
    minute_start = minute_cutoff - timedelta(minutes=1)
    completed_interval_session = MarketCalendar().session_at(minute_start)
    if completed_interval_session is None or (
        completed_interval_session is MarketSession.OVERNIGHT and not entitlement.overnight
    ):
        data_cutoff = latest_completed_market_cutoff(requested_at, cutoff=time(16))
        timeframe = BarTimeframe.DAY
        window_start = data_cutoff - timedelta(days=1)
        request_session = MarketSession.REGULAR
    else:
        data_cutoff = minute_cutoff
        timeframe = BarTimeframe.MINUTE
        window_start = minute_start
        request_session = completed_interval_session

    observed_entitlement = replace(entitlement, observed_at=requested_at)
    admitted_ids: list[UUID] = []
    created_ids: list[UUID] = []
    for symbol in normalized_symbols:
        scheduled = schedule_alpaca_backfills(
            store,
            symbol=symbol,
            dataset=FeedType.PRICE_BARS,
            timeframe=timeframe,
            start=window_start,
            end=data_cutoff,
            purpose=DataPurpose.REALTIME_CONTEXT,
            required_coverage=feed,
            session=request_session,
            entitlement=observed_entitlement,
            now=requested_at,
            max_jobs=1,
        )
        admitted_ids.extend(scheduled.job_ids)
        created_ids.extend(scheduled.created_job_ids)

    job_ids = tuple(dict.fromkeys(admitted_ids))
    newly_created = frozenset(created_ids)
    published = 0
    for job_id in job_ids:
        if job_id in newly_created and is_queued(job_id):
            publish(ALPACA_INGESTION_TASK, job_id, ALPACA_INGESTION_QUEUE)
            published += 1

    if published:
        status = WatchlistRefreshStatus.QUEUED
        message = "Latest Watchlist market-data jobs were queued."
    elif job_ids:
        status = WatchlistRefreshStatus.ALREADY_QUEUED
        message = "Equivalent Watchlist market-data jobs are already active."
    else:
        status = WatchlistRefreshStatus.UNAVAILABLE
        message = "The requested Alpaca IEX session is unavailable."

    return WatchlistRefreshResult(
        status=status,
        job_ids=job_ids,
        symbol_count=len(normalized_symbols),
        requested_at=requested_at,
        data_cutoff=data_cutoff,
        timeframe=timeframe,
        feed=feed,
        message=message,
    )
