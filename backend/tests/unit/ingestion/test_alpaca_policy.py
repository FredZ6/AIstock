from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pytest
from stock_platform.application.ingestion.normalizers.alpaca import market_session_for
from stock_platform.application.market_data.policy import (
    EntitlementSnapshot,
    MarketCalendar,
    PolicyOutcome,
    alpaca_entitlement_from_settings,
    route_market_data,
)
from stock_platform.domain.ingestion.models import (
    DataPurpose,
    MarketDataCoverage,
    MarketSession,
)
from stock_platform.settings import Settings

NOW = datetime(2026, 8, 24, tzinfo=UTC)


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


def test_default_market_calendar_knows_nyse_holidays_and_early_closes() -> None:
    calendar = MarketCalendar()

    assert calendar.session_at(datetime(2026, 12, 25, 15, tzinfo=UTC)) is None
    assert calendar.session_at(datetime(2026, 11, 27, 19, tzinfo=UTC)) is MarketSession.AFTER_HOURS


def test_market_calendar_rejects_naive_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        MarketCalendar().session_at(datetime(2026, 8, 24, 10))


def test_normalized_market_session_rejects_naive_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        market_session_for(datetime(2026, 8, 24, 10))


def test_normalized_market_session_uses_holiday_and_half_day_calendar() -> None:
    calendar = MarketCalendar(
        closures=frozenset({date(2026, 12, 25)}),
        half_days={date(2026, 11, 27): time(13)},
    )

    assert market_session_for(datetime(2026, 12, 25, 15, tzinfo=UTC), calendar=calendar) is None
    assert (
        market_session_for(datetime(2026, 11, 27, 19, tzinfo=UTC), calendar=calendar)
        is MarketSession.AFTER_HOURS
    )


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


def test_runtime_entitlement_requires_explicit_credentials_coverage_and_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in (
        "ALPACA_DATA_KEY",
        "ALPACA_DATA_SECRET",
        "ALPACA_ENTITLEMENT_COVERAGE",
        "ALPACA_ENTITLEMENT_VERSION",
        "ALPACA_SIP_DELAY_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    assert alpaca_entitlement_from_settings(Settings(environment="test"), observed_at=NOW) is None
    with pytest.raises(ValueError, match="configured together"):
        Settings(environment="test", alpaca_data_key="key-only")
    with pytest.raises(ValueError, match="entitlement version"):
        Settings(
            environment="test",
            alpaca_data_key="key",
            alpaca_data_secret="secret",
            alpaca_entitlement_coverage="IEX",
        )

    snapshot = alpaca_entitlement_from_settings(
        Settings(
            environment="test",
            alpaca_data_key="key",
            alpaca_data_secret="secret",
            alpaca_entitlement_coverage="IEX,SIP",
            alpaca_entitlement_version="operator-verified-2026-08-24",
            alpaca_sip_delay_seconds=900,
        ),
        observed_at=NOW,
    )

    assert snapshot is not None
    assert snapshot.coverage == frozenset({MarketDataCoverage.IEX, MarketDataCoverage.SIP})
    assert snapshot.version == "operator-verified-2026-08-24"
    assert snapshot.sip_delay == timedelta(minutes=15)
