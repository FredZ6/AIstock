from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from stock_platform.application.market_data.reconciliation import (
    BarObservation,
    ReconciliationKind,
    reconcile_bars,
    reconcile_minute_to_daily,
)
from stock_platform.domain.ingestion.models import MarketDataCoverage, MarketSession

START = datetime(2026, 8, 27, 13, 30, tzinfo=UTC)


def _bar(
    minute: int,
    *,
    coverage: MarketDataCoverage = MarketDataCoverage.SIP,
    open_: str = "100",
    high: str = "102",
    low: str = "99",
    close: str = "101",
    volume: str = "10",
    available_offset: int = 1,
) -> BarObservation:
    event_time = START + timedelta(minutes=minute)
    return BarObservation(
        normalized_record_id=uuid4(),
        symbol="NVDA",
        event_time=event_time,
        available_at=event_time + timedelta(seconds=available_offset),
        coverage=coverage,
        session=MarketSession.REGULAR,
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal(volume),
    )


def test_reconciliation_detects_missing_interval_duplicate_and_revision() -> None:
    original = _bar(0)
    duplicate = BarObservation(
        normalized_record_id=uuid4(),
        symbol=original.symbol,
        event_time=original.event_time,
        available_at=original.available_at + timedelta(seconds=1),
        coverage=original.coverage,
        session=original.session,
        open=original.open,
        high=original.high,
        low=original.low,
        close=original.close,
        volume=original.volume,
    )
    revision = _bar(0, close="100.5", available_offset=3)

    findings = reconcile_bars(
        (original, duplicate, revision, _bar(2)),
        expected_interval=timedelta(minutes=1),
    )

    assert {finding.kind for finding in findings} == {
        ReconciliationKind.MISSING_INTERVAL,
        ReconciliationKind.DUPLICATE,
        ReconciliationKind.REVISION,
    }


def test_reconciliation_detects_invalid_ohlc_and_volume() -> None:
    findings = reconcile_bars(
        (_bar(0, high="98", low="103"), _bar(1, volume="-1")),
        expected_interval=timedelta(minutes=1),
    )

    assert [finding.kind for finding in findings].count(ReconciliationKind.OHLC_INVALID) == 1
    assert [finding.kind for finding in findings].count(ReconciliationKind.VOLUME_INVALID) == 1


def test_iex_and_sip_are_separate_coverage_series_not_conflicts() -> None:
    findings = reconcile_bars(
        (
            _bar(0, coverage=MarketDataCoverage.IEX, close="100"),
            _bar(0, coverage=MarketDataCoverage.SIP, close="101"),
        ),
        expected_interval=timedelta(minutes=1),
    )

    assert findings == ()


def test_minute_to_daily_volume_mismatch_is_deterministic_and_coverage_scoped() -> None:
    daily = _bar(0, volume="25")
    mismatch = reconcile_minute_to_daily((_bar(0, volume="10"), _bar(1, volume="10")), daily)
    other_coverage = reconcile_minute_to_daily(
        (_bar(0, coverage=MarketDataCoverage.IEX, volume="25"),),
        daily,
    )

    assert tuple(finding.kind for finding in mismatch) == (ReconciliationKind.VOLUME_MISMATCH,)
    assert other_coverage == ()
