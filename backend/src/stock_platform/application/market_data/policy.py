"""Entitlement-aware market-data routing and exchange-session policy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from stock_platform.domain.common.time import require_aware
from stock_platform.domain.ingestion.models import (
    DataPurpose,
    MarketDataCoverage,
    MarketSession,
)
from stock_platform.domain.research.evidence import EvidenceGapKind

NEW_YORK = ZoneInfo("America/New_York")


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
        if local.weekday() >= 5 or local.date() in self.closures:
            return None
        local_time = local.time().replace(tzinfo=None)
        close = (self.half_days or {}).get(local.date(), time(16))
        if time(4) <= local_time < time(9, 30):
            return MarketSession.PRE_MARKET
        if time(9, 30) <= local_time < close:
            return MarketSession.REGULAR
        if close <= local_time < time(20):
            return MarketSession.AFTER_HOURS
        return MarketSession.OVERNIGHT


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
