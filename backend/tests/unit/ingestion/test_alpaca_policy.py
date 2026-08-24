from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta

import pytest
from stock_platform.application.market_data.policy import (
    EntitlementSnapshot,
    MarketCalendar,
    PolicyOutcome,
    route_market_data,
)
from stock_platform.domain.ingestion.models import (
    DataPurpose,
    MarketDataCoverage,
    MarketSession,
)


def _entitlement(*coverage: MarketDataCoverage, overnight: bool = False) -> EntitlementSnapshot:
    return EntitlementSnapshot(
        provider="ALPACA",
        coverage=frozenset(coverage),
        overnight=overnight,
        sip_delay=timedelta(minutes=15) if MarketDataCoverage.SIP in coverage else None,
        observed_at=datetime(2026, 8, 24, tzinfo=UTC),
        version="alpaca-entitlement-v1",
    )


def test_market_calendar_handles_dst_holiday_and_half_day() -> None:
    calendar = MarketCalendar(
        closures=frozenset({date(2026, 12, 25)}),
        half_days={date(2026, 11, 27): time(13)},
    )

    assert calendar.session_at(datetime(2026, 1, 5, 14, 30, tzinfo=UTC)) is MarketSession.REGULAR
    assert calendar.session_at(datetime(2026, 7, 6, 13, 30, tzinfo=UTC)) is MarketSession.REGULAR
    assert calendar.session_at(datetime(2026, 12, 25, 15, tzinfo=UTC)) is None
    assert calendar.session_at(datetime(2026, 11, 27, 17, 59, tzinfo=UTC)) is MarketSession.REGULAR
    assert (
        calendar.session_at(datetime(2026, 11, 27, 18, 1, tzinfo=UTC)) is MarketSession.AFTER_HOURS
    )


def test_market_calendar_rejects_naive_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        MarketCalendar().session_at(datetime(2026, 8, 24, 10))


def test_entitlement_policy_never_relables_iex_as_sip() -> None:
    entitlement = _entitlement(MarketDataCoverage.IEX)

    research = route_market_data(
        purpose=DataPurpose.RESEARCH,
        required_coverage=MarketDataCoverage.SIP,
        session=MarketSession.REGULAR,
        entitlement=entitlement,
    )
    assert research.outcome is PolicyOutcome.ALLOWED_WITH_GAP
    assert research.selected_coverage is MarketDataCoverage.IEX
    assert research.gap_kind == "UNAVAILABLE"
    assert research.entitlement_version == "alpaca-entitlement-v1"

    for purpose in (DataPurpose.REPLAY, DataPurpose.PAPER_EXECUTION):
        denied = route_market_data(
            purpose=purpose,
            required_coverage=MarketDataCoverage.SIP,
            session=MarketSession.REGULAR,
            entitlement=entitlement,
        )
        assert denied.outcome is PolicyOutcome.DENIED_NO_ACTION
        assert denied.selected_coverage is None
        assert denied.gap_kind == "UNAVAILABLE"


def test_coverage_and_overnight_entitlements_remain_separate() -> None:
    sip = _entitlement(MarketDataCoverage.IEX, MarketDataCoverage.SIP)
    decision = route_market_data(
        purpose=DataPurpose.PAPER_EXECUTION,
        required_coverage=MarketDataCoverage.SIP,
        session=MarketSession.REGULAR,
        entitlement=sip,
    )
    assert decision.outcome is PolicyOutcome.ALLOWED
    assert decision.selected_coverage is MarketDataCoverage.SIP
    assert decision.declared_delay == timedelta(minutes=15)

    overnight = route_market_data(
        purpose=DataPurpose.RESEARCH,
        required_coverage=MarketDataCoverage.IEX,
        session=MarketSession.OVERNIGHT,
        entitlement=sip,
    )
    assert overnight.outcome is PolicyOutcome.ALLOWED_WITH_GAP
    assert overnight.selected_coverage is None


def test_entitlement_metadata_requires_aware_observation_and_declared_sip_delay() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        EntitlementSnapshot(
            provider="ALPACA",
            coverage=frozenset({MarketDataCoverage.IEX}),
            overnight=False,
            sip_delay=None,
            observed_at=datetime(2026, 8, 24),
            version="v1",
        )
    with pytest.raises(ValueError, match="SIP delay"):
        replace(_entitlement(MarketDataCoverage.SIP), sip_delay=None)
