"""Immutable decision outcomes computed from point-in-time market facts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import IntEnum
from types import MappingProxyType
from uuid import UUID, uuid4

from stock_platform.domain.common.time import require_aware
from stock_platform.domain.research.claims import ResearchOpinionValue


class Horizon(IntEnum):
    DAY_1 = 1
    DAY_5 = 5
    DAY_20 = 20
    DAY_60 = 60


@dataclass(frozen=True, slots=True)
class DecisionForReview:
    id: UUID
    symbol: str
    decision_time: datetime
    reference_price: Decimal
    opinion: ResearchOpinionValue = ResearchOpinionValue.NEUTRAL
    data_complete: bool = True
    data_fresh: bool = True
    evidence_conflicted: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_time", require_aware(self.decision_time).astimezone(UTC))
        if not self.symbol.strip():
            raise ValueError("symbol is required")
        if not isinstance(self.reference_price, Decimal):
            raise TypeError("reference price must use Decimal")
        if not self.reference_price.is_finite() or self.reference_price <= 0:
            raise ValueError("reference price must be finite and positive")
        object.__setattr__(self, "opinion", ResearchOpinionValue(self.opinion))


@dataclass(frozen=True, slots=True)
class PriceObservation:
    event_time: datetime
    available_at: datetime
    price: Decimal

    def __post_init__(self) -> None:
        event_time = require_aware(self.event_time).astimezone(UTC)
        available_at = require_aware(self.available_at).astimezone(UTC)
        if not isinstance(self.price, Decimal):
            raise TypeError("price must use Decimal")
        if not self.price.is_finite() or self.price <= 0:
            raise ValueError("price must be finite and positive")
        object.__setattr__(self, "event_time", event_time)
        object.__setattr__(self, "available_at", available_at)


@dataclass(frozen=True, slots=True)
class DecisionOutcome:
    id: UUID
    decision_id: UUID
    status: str
    returns: Mapping[Horizon, Decimal]
    excess_returns: Mapping[Horizon, Decimal]
    maximum_favorable_excursion: Decimal
    maximum_adverse_excursion: Decimal
    risk_adjusted_return: Decimal
    calibration_error: Decimal
    computed_at: datetime


def _visible(
    observations: tuple[PriceObservation, ...], as_of: datetime
) -> tuple[PriceObservation, ...]:
    if any(item.available_at > as_of for item in observations):
        raise ValueError("price observation was not available at outcome cutoff")
    return tuple(sorted(observations, key=lambda item: (item.event_time, item.available_at)))


def _price_at_or_after(
    observations: tuple[PriceObservation, ...], target: datetime
) -> Decimal | None:
    return next((item.price for item in observations if item.event_time >= target), None)


def compute_outcome(
    decision: DecisionForReview,
    *,
    prices: tuple[PriceObservation, ...],
    benchmark_prices: tuple[PriceObservation, ...],
    as_of: datetime,
) -> DecisionOutcome:
    cutoff = require_aware(as_of).astimezone(UTC)
    visible_prices = _visible(prices, cutoff)
    visible_benchmark = _visible(benchmark_prices, cutoff)
    matured = tuple(
        horizon
        for horizon in Horizon
        if decision.decision_time + timedelta(days=int(horizon)) <= cutoff
    )
    returns: dict[Horizon, Decimal] = {}
    excess: dict[Horizon, Decimal] = {}
    benchmark_history = tuple(
        item.price for item in visible_benchmark if item.event_time <= decision.decision_time
    )
    benchmark_base = benchmark_history[-1] if benchmark_history else None
    for horizon in matured:
        target = decision.decision_time + timedelta(days=int(horizon))
        price = _price_at_or_after(visible_prices, target)
        if price is None:
            continue
        realized = price / decision.reference_price - Decimal("1")
        returns[horizon] = realized
        benchmark_price = _price_at_or_after(visible_benchmark, target)
        if benchmark_base is not None and benchmark_price is not None:
            benchmark_return = benchmark_price / benchmark_base - Decimal("1")
            excess[horizon] = realized - benchmark_return
    path_returns = tuple(
        item.price / decision.reference_price - Decimal("1")
        for item in visible_prices
        if item.event_time >= decision.decision_time
    )
    favorable = max((Decimal("0"), *path_returns))
    adverse = min((Decimal("0"), *path_returns))
    terminal = returns[max(returns)] if returns else Decimal("0")
    downside = abs(adverse) or Decimal("1")
    expected = {
        ResearchOpinionValue.BULLISH: Decimal("1"),
        ResearchOpinionValue.BEARISH: Decimal("-1"),
        ResearchOpinionValue.NEUTRAL: Decimal("0"),
        ResearchOpinionValue.ABSTAIN: Decimal("0"),
    }[decision.opinion]
    realized_direction = (
        Decimal("1") if terminal > 0 else Decimal("-1") if terminal < 0 else Decimal("0")
    )
    return DecisionOutcome(
        id=uuid4(),
        decision_id=decision.id,
        status="MATURED" if returns else "PENDING",
        returns=MappingProxyType(returns),
        excess_returns=MappingProxyType(excess),
        maximum_favorable_excursion=favorable,
        maximum_adverse_excursion=adverse,
        risk_adjusted_return=terminal / downside,
        calibration_error=abs(expected - realized_direction),
        computed_at=cutoff,
    )
