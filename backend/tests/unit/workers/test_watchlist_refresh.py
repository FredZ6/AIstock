from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from stock_platform.application.ingestion.jobs import (
    IngestionJobAdmission,
    IngestionJobSpec,
)
from stock_platform.application.ingestion.watchlist_refresh import (
    WatchlistRefreshResult,
    WatchlistRefreshStatus,
    request_watchlist_market_data_refresh,
)
from stock_platform.application.market_data.policy import EntitlementSnapshot
from stock_platform.domain.ingestion.models import (
    DataPurpose,
    MarketDataCoverage,
    MarketSession,
)
from stock_platform.workers.ingestion_tasks import BarTimeframe


class RecordingJobStore:
    def __init__(self, job_ids: tuple[UUID, ...] = ()) -> None:
        self.specs: list[IngestionJobSpec] = []
        self._job_ids = iter(job_ids)

    def enqueue_with_result(
        self, spec: IngestionJobSpec, *, now: datetime
    ) -> IngestionJobAdmission:
        self.specs.append(spec)
        return IngestionJobAdmission(next(self._job_ids, uuid4()), created=True)


class IdempotentRecordingJobStore:
    def __init__(self) -> None:
        self.specs: list[IngestionJobSpec] = []
        self._job_ids_by_request: dict[str, UUID] = {}

    def enqueue_with_result(
        self, spec: IngestionJobSpec, *, now: datetime
    ) -> IngestionJobAdmission:
        self.specs.append(spec)
        existing = self._job_ids_by_request.get(spec.request.request_hash)
        if existing is not None:
            return IngestionJobAdmission(existing, created=False)
        job_id = uuid4()
        self._job_ids_by_request[spec.request.request_hash] = job_id
        return IngestionJobAdmission(job_id, created=True)


def alpaca_entitlement(*coverage: MarketDataCoverage) -> EntitlementSnapshot:
    return EntitlementSnapshot(
        provider="ALPACA",
        coverage=frozenset(coverage),
        overnight=False,
        sip_delay=(timedelta(0) if MarketDataCoverage.SIP in coverage else None),
        observed_at=datetime(2026, 10, 5, tzinfo=UTC),
        version="operator-verified-2026-08-31",
    )


def request_refresh(
    *,
    store: RecordingJobStore,
    symbols: tuple[str, ...] = ("NVDA",),
    now: datetime = datetime(2026, 10, 5, 14, 31, 42, tzinfo=UTC),
    entitlement: EntitlementSnapshot | None = None,
    eligible: set[UUID] | None = None,
) -> tuple[WatchlistRefreshResult, list[tuple[str, UUID, str]]]:
    published: list[tuple[str, UUID, str]] = []
    result = request_watchlist_market_data_refresh(
        store=store,
        symbols=symbols,
        entitlement=entitlement or alpaca_entitlement(MarketDataCoverage.IEX),
        now=now,
        is_queued=(lambda job_id: eligible is None or job_id in eligible),
        publish=lambda task, job_id, queue: published.append((task, job_id, queue)),
    )
    return result, published


def test_active_session_requests_latest_completed_minute_for_every_monitored_symbol() -> None:
    now = datetime(2026, 10, 5, 14, 31, 42, tzinfo=UTC)
    store = RecordingJobStore()

    result, published = request_refresh(
        store=store,
        symbols=("AVGO", "NVDA"),
        now=now,
    )

    assert result.status is WatchlistRefreshStatus.QUEUED
    assert result.timeframe is BarTimeframe.MINUTE
    assert result.data_cutoff == datetime(2026, 10, 5, 14, 31, tzinfo=UTC)
    assert result.requested_at == now
    assert result.symbol_count == 2
    assert result.feed is MarketDataCoverage.IEX
    assert {spec.request.canonical_payload["symbol"] for spec in store.specs} == {
        "AVGO",
        "NVDA",
    }
    assert all(
        spec.window_start == datetime(2026, 10, 5, 14, 30, tzinfo=UTC) for spec in store.specs
    )
    assert all(spec.window_end == result.data_cutoff for spec in store.specs)
    assert all(spec.purpose is DataPurpose.REALTIME_CONTEXT for spec in store.specs)
    assert all(
        spec.request.canonical_payload["session"] == MarketSession.REGULAR.value
        for spec in store.specs
    )
    assert len(published) == 2
    assert all(
        task == "stock_platform.workers.ingestion_tasks.run_alpaca_ingestion_job"
        and queue == "ingestion-low"
        for task, _job_id, queue in published
    )


def test_closed_session_requests_latest_completed_trading_day() -> None:
    now = datetime(2026, 10, 4, 12, tzinfo=UTC)
    store = RecordingJobStore()

    result, _ = request_refresh(store=store, now=now)

    assert result.timeframe is BarTimeframe.DAY
    assert result.data_cutoff == datetime(2026, 10, 2, 20, tzinfo=UTC)
    assert store.specs[0].window_start == datetime(2026, 10, 1, 20, tzinfo=UTC)
    assert store.specs[0].window_end == result.data_cutoff
    assert store.specs[0].purpose is DataPurpose.REALTIME_CONTEXT
    assert store.specs[0].request.canonical_payload["session"] == MarketSession.REGULAR.value


@pytest.mark.parametrize(
    ("now", "expected_session"),
    [
        (datetime(2026, 10, 5, 13, 30, 42, tzinfo=UTC), MarketSession.PRE_MARKET),
        (datetime(2026, 10, 5, 20, 0, 42, tzinfo=UTC), MarketSession.REGULAR),
        (datetime(2026, 10, 6, 0, 0, 42, tzinfo=UTC), MarketSession.AFTER_HOURS),
    ],
)
def test_boundary_minute_uses_session_covering_the_completed_interval(
    now: datetime,
    expected_session: MarketSession,
) -> None:
    store = RecordingJobStore()

    result, _ = request_refresh(store=store, now=now)

    assert result.timeframe is BarTimeframe.MINUTE
    assert store.specs[0].window_start == now.replace(second=0) - timedelta(minutes=1)
    assert store.specs[0].request.canonical_payload["session"] == expected_session.value


def test_unentitled_overnight_interval_falls_back_to_latest_completed_day() -> None:
    now = datetime(2026, 10, 6, 0, 1, 42, tzinfo=UTC)
    store = RecordingJobStore()

    result, published = request_refresh(store=store, now=now)

    assert result.status is WatchlistRefreshStatus.QUEUED
    assert result.timeframe is BarTimeframe.DAY
    assert result.data_cutoff == datetime(2026, 10, 5, 20, tzinfo=UTC)
    assert store.specs[0].window_start == datetime(2026, 10, 4, 20, tzinfo=UTC)
    assert store.specs[0].request.canonical_payload["session"] == MarketSession.REGULAR.value
    assert len(published) == 1


def test_closed_holiday_weekend_uses_latest_completed_trading_day() -> None:
    now = datetime(2026, 7, 5, 12, tzinfo=UTC)
    store = RecordingJobStore()

    result, _ = request_refresh(store=store, now=now)

    assert result.timeframe is BarTimeframe.DAY
    assert result.data_cutoff == datetime(2026, 7, 2, 20, tzinfo=UTC)


def test_refresh_rejects_naive_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        request_refresh(
            store=RecordingJobStore(),
            now=datetime(2026, 10, 5, 14, 31),
        )


def test_only_supplied_monitored_symbols_are_scheduled() -> None:
    store = RecordingJobStore()

    result, _ = request_refresh(store=store, symbols=("  nvda  ", "AVGO"))

    assert result.symbol_count == 2
    assert [spec.request.canonical_payload["symbol"] for spec in store.specs] == [
        "NVDA",
        "AVGO",
    ]


def test_zero_symbols_returns_no_symbols_without_publishing() -> None:
    store = RecordingJobStore()

    result, published = request_refresh(store=store, symbols=())

    assert result.status is WatchlistRefreshStatus.NO_SYMBOLS
    assert result.job_ids == ()
    assert result.symbol_count == 0
    assert result.data_cutoff is None
    assert result.timeframe is None
    assert result.feed is MarketDataCoverage.IEX
    assert store.specs == []
    assert published == []


def test_refresh_always_selects_iex_from_operator_entitlement() -> None:
    store = RecordingJobStore()

    result, _ = request_refresh(
        store=store,
        entitlement=alpaca_entitlement(MarketDataCoverage.IEX, MarketDataCoverage.SIP),
    )

    assert result.feed is MarketDataCoverage.IEX
    assert store.specs[0].request.canonical_payload["coverage"] == MarketDataCoverage.IEX.value


@pytest.mark.parametrize(
    "entitlement",
    [
        None,
        EntitlementSnapshot(
            provider="OTHER",
            coverage=frozenset({MarketDataCoverage.IEX}),
            overnight=False,
            sip_delay=None,
            observed_at=datetime(2026, 10, 5, tzinfo=UTC),
            version="other-v1",
        ),
        alpaca_entitlement(MarketDataCoverage.SIP),
    ],
)
def test_invalid_or_non_iex_entitlement_is_explicitly_unavailable(
    entitlement: EntitlementSnapshot | None,
) -> None:
    store = RecordingJobStore()
    published: list[tuple[str, UUID, str]] = []

    result = request_watchlist_market_data_refresh(
        store=store,
        symbols=("NVDA",),
        entitlement=entitlement,
        now=datetime(2026, 10, 5, 14, 31, tzinfo=UTC),
        is_queued=lambda _job_id: True,
        publish=lambda task, job_id, queue: published.append((task, job_id, queue)),
    )

    assert result.status is WatchlistRefreshStatus.UNAVAILABLE
    assert result.job_ids == ()
    assert result.feed is None
    assert store.specs == []
    assert published == []


def test_duplicate_job_ids_are_deduplicated_before_publish() -> None:
    shared_id = uuid4()
    store = RecordingJobStore((shared_id, shared_id))

    result, published = request_refresh(store=store, symbols=("NVDA", "AVGO"))

    assert result.job_ids == (shared_id,)
    assert published == [
        (
            "stock_platform.workers.ingestion_tasks.run_alpaca_ingestion_job",
            shared_id,
            "ingestion-low",
        )
    ]


def test_only_confirmed_queued_jobs_are_published() -> None:
    queued_id = uuid4()
    running_id = uuid4()
    store = RecordingJobStore((queued_id, running_id))

    result, published = request_refresh(
        store=store,
        symbols=("NVDA", "AVGO"),
        eligible={queued_id},
    )

    assert result.status is WatchlistRefreshStatus.QUEUED
    assert result.job_ids == (queued_id, running_id)
    assert published == [
        (
            "stock_platform.workers.ingestion_tasks.run_alpaca_ingestion_job",
            queued_id,
            "ingestion-low",
        )
    ]


def test_existing_nonqueued_jobs_report_already_queued_without_publish() -> None:
    existing_id = uuid4()
    store = RecordingJobStore((existing_id,))

    result, published = request_refresh(store=store, eligible=set())

    assert result.status is WatchlistRefreshStatus.ALREADY_QUEUED
    assert result.job_ids == (existing_id,)
    assert published == []


def test_repeat_request_reuses_ids_without_republishing() -> None:
    store = IdempotentRecordingJobStore()
    published: list[tuple[str, UUID, str]] = []

    def request() -> WatchlistRefreshResult:
        return request_watchlist_market_data_refresh(
            store=store,
            symbols=("NVDA", "AVGO"),
            entitlement=alpaca_entitlement(MarketDataCoverage.IEX),
            now=datetime(2026, 10, 5, 14, 31, 42, tzinfo=UTC),
            is_queued=lambda _job_id: True,
            publish=lambda task, job_id, queue: published.append(
                (
                    task,
                    job_id,
                    queue,
                )
            ),
        )

    first = request()
    first_publish_count = len(published)
    second = request()

    assert first.status is WatchlistRefreshStatus.QUEUED
    assert first_publish_count == 2
    assert second.job_ids == first.job_ids
    assert second.status is WatchlistRefreshStatus.ALREADY_QUEUED
    assert len(published) == first_publish_count


def test_refresh_service_has_no_research_portfolio_or_broker_execution_dependency() -> None:
    module = inspect.getmodule(request_watchlist_market_data_refresh)
    assert module is not None
    source = inspect.getsource(module)

    assert "research" not in source.lower()
    assert "portfolio" not in source.lower()
    assert "broker" not in source.lower()
