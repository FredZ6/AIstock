"""Entitlement-aware market-data routing and exchange-session policy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from stock_platform.domain.common.time import require_aware
from stock_platform.domain.ingestion.models import (
    DataPurpose,
    MarketDataCoverage,
    MarketSession,
)
from stock_platform.domain.research.evidence import EvidenceGapKind

if TYPE_CHECKING:
    from stock_platform.settings import Settings

NEW_YORK = ZoneInfo("America/New_York")


def _observed(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (occurrence - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    first_next_month = date(year + (month == 12), month % 12 + 1, 1)
    last = first_next_month - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _easter_sunday(year: int) -> date:
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = (h + ell - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def _nyse_closures(year: int) -> frozenset[date]:
    holidays = {
        _observed(date(year, 1, 1)),
        _nth_weekday(year, 1, 0, 3),
        _nth_weekday(year, 2, 0, 3),
        _easter_sunday(year) - timedelta(days=2),
        _last_weekday(year, 5, 0),
        _observed(date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),
        _nth_weekday(year, 11, 3, 4),
        _observed(date(year, 12, 25)),
    }
    if year >= 2022:
        holidays.add(_observed(date(year, 6, 19)))
    return frozenset(holidays)


def _nyse_half_days(year: int) -> dict[date, time]:
    thanksgiving = _nth_weekday(year, 11, 3, 4)
    candidates = {
        thanksgiving + timedelta(days=1),
        date(year, 7, 3),
        date(year, 12, 24),
    }
    closures = _nyse_closures(year)
    return {day: time(13) for day in candidates if day.weekday() < 5 and day not in closures}


class PolicyOutcome(StrEnum):
    ALLOWED = "ALLOWED"
    ALLOWED_WITH_GAP = "ALLOWED_WITH_GAP"
    DENIED_NO_ACTION = "DENIED_NO_ACTION"


@dataclass(frozen=True, slots=True)
class EntitlementSnapshot:
    provider: str
    coverage: frozenset[MarketDataCoverage]
    overnight: bool
    sip_delay: timedelta | None
    observed_at: datetime
    version: str

    def __post_init__(self) -> None:
        if not self.provider or not self.version:
            raise ValueError("provider and entitlement version are required")
        observed = require_aware(self.observed_at).astimezone(UTC)
        if MarketDataCoverage.SIP in self.coverage:
            if self.sip_delay is None or self.sip_delay < timedelta(0):
                raise ValueError("SIP delay must be explicitly declared")
        elif self.sip_delay is not None:
            raise ValueError("SIP delay cannot be declared without SIP coverage")
        object.__setattr__(self, "observed_at", observed)


@dataclass(frozen=True, slots=True)
class MarketDataDecision:
    outcome: PolicyOutcome
    selected_coverage: MarketDataCoverage | None
    gap_kind: str | None
    reason: str | None
    entitlement_version: str
    declared_delay: timedelta | None


@dataclass(frozen=True, slots=True)
class MarketCalendar:
    closures: frozenset[date] = frozenset()
    half_days: Mapping[date, time] | None = None

    def session_at(self, value: datetime) -> MarketSession | None:
        local = require_aware(value).astimezone(NEW_YORK)
        closures = set(self.closures)
        for year in (local.year - 1, local.year, local.year + 1):
            closures.update(_nyse_closures(year))
        if local.weekday() >= 5 or local.date() in closures:
            return None
        local_time = local.time().replace(tzinfo=None)
        half_days = _nyse_half_days(local.year)
        half_days.update(self.half_days or {})
        close = half_days.get(local.date(), time(16))
        if time(4) <= local_time < time(9, 30):
            return MarketSession.PRE_MARKET
        if time(9, 30) <= local_time < close:
            return MarketSession.REGULAR
        if close <= local_time < time(20):
            return MarketSession.AFTER_HOURS
        return MarketSession.OVERNIGHT


def alpaca_entitlement_from_settings(
    settings: Settings,
    *,
    observed_at: datetime,
) -> EntitlementSnapshot | None:
    if (
        settings.alpaca_data_key is None
        or settings.alpaca_data_secret is None
        or settings.alpaca_entitlement_coverage is None
        or settings.alpaca_entitlement_version is None
    ):
        return None
    coverage = frozenset(
        MarketDataCoverage(value.strip().upper())
        for value in settings.alpaca_entitlement_coverage.split(",")
        if value.strip()
    )
    return EntitlementSnapshot(
        provider="ALPACA",
        coverage=coverage,
        overnight=settings.alpaca_overnight,
        sip_delay=(
            timedelta(seconds=settings.alpaca_sip_delay_seconds)
            if settings.alpaca_sip_delay_seconds is not None
            else None
        ),
        observed_at=observed_at,
        version=settings.alpaca_entitlement_version,
    )


def route_market_data(
    *,
    purpose: DataPurpose,
    required_coverage: MarketDataCoverage,
    session: MarketSession,
    entitlement: EntitlementSnapshot,
) -> MarketDataDecision:
    session_available = session is not MarketSession.OVERNIGHT or entitlement.overnight
    coverage_available = required_coverage in entitlement.coverage
    if session_available and coverage_available:
        return MarketDataDecision(
            outcome=PolicyOutcome.ALLOWED,
            selected_coverage=required_coverage,
            gap_kind=None,
            reason=None,
            entitlement_version=entitlement.version,
            declared_delay=(
                entitlement.sip_delay if required_coverage is MarketDataCoverage.SIP else None
            ),
        )

    reason = (
        "overnight entitlement unavailable"
        if not session_available
        else f"{required_coverage.value} entitlement unavailable"
    )
    if purpose is DataPurpose.RESEARCH:
        fallback = (
            MarketDataCoverage.IEX
            if session_available and MarketDataCoverage.IEX in entitlement.coverage
            else None
        )
        return MarketDataDecision(
            outcome=PolicyOutcome.ALLOWED_WITH_GAP,
            selected_coverage=fallback,
            gap_kind=EvidenceGapKind.UNAVAILABLE.value,
            reason=reason,
            entitlement_version=entitlement.version,
            declared_delay=None,
        )
    return MarketDataDecision(
        outcome=PolicyOutcome.DENIED_NO_ACTION,
        selected_coverage=None,
        gap_kind=EvidenceGapKind.UNAVAILABLE.value,
        reason=reason,
        entitlement_version=entitlement.version,
        declared_delay=None,
    )


def paper_market_data_admission(
    settings: Settings,
    *,
    cutoff: datetime,
    purpose: DataPurpose,
) -> MarketDataDecision | None:
    """Shared API/Beat admission boundary; explicit Fixture mode bypasses live entitlement."""
    if settings.fixture_mode:
        return None
    observed_at = require_aware(cutoff).astimezone(UTC)
    entitlement = alpaca_entitlement_from_settings(settings, observed_at=observed_at)
    if entitlement is None:
        entitlement = EntitlementSnapshot(
            provider="ALPACA",
            coverage=frozenset(),
            overnight=False,
            sip_delay=None,
            observed_at=observed_at,
            version="alpaca-unconfigured",
        )
    return route_market_data(
        purpose=purpose,
        required_coverage=MarketDataCoverage.SIP,
        session=MarketSession.REGULAR,
        entitlement=entitlement,
    )


def admission_payload(decision: MarketDataDecision) -> dict[str, object]:
    return {
        "market_data_admission": {
            "outcome": decision.outcome.value,
            "selected_coverage": (
                decision.selected_coverage.value if decision.selected_coverage is not None else None
            ),
            "gap_kind": decision.gap_kind,
            "reason": decision.reason,
            "entitlement_version": decision.entitlement_version,
            "declared_delay_seconds": (
                int(decision.declared_delay.total_seconds())
                if decision.declared_delay is not None
                else None
            ),
        }
    }
