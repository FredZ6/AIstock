from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from stock_platform.domain.common.time import require_aware
from stock_platform.domain.research.claims import ResearchOpinionValue


class PortfolioActionValue(StrEnum):
    ENTER = "ENTER"
    ADD = "ADD"
    HOLD = "HOLD"
    REDUCE = "REDUCE"
    EXIT = "EXIT"
    NO_ACTION = "NO_ACTION"


class MarketRegime(StrEnum):
    RISK_ON = "RISK_ON"
    MIXED = "MIXED"
    RISK_OFF = "RISK_OFF"


@dataclass(frozen=True, slots=True)
class MarketContextSnapshot:
    id: UUID
    as_of: datetime
    available_at: datetime
    qqq_trend: Decimal
    qqq_volatility: Decimal
    soxx_relative_strength: Decimal
    vix: Decimal
    regime: MarketRegime
    algorithm_version: str
    source_lineage: tuple[UUID, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", require_aware(self.as_of).astimezone(UTC))
        object.__setattr__(
            self,
            "available_at",
            require_aware(self.available_at).astimezone(UTC),
        )
        if self.available_at < self.as_of:
            raise ValueError("market context cannot be available before its event time")
        for name in (
            "qqq_trend",
            "qqq_volatility",
            "soxx_relative_strength",
            "vix",
        ):
            value = getattr(self, name)
            if not isinstance(value, Decimal):
                raise TypeError(f"{name} must use Decimal")
            if not value.is_finite():
                raise ValueError(f"{name} must be finite")
        if self.qqq_volatility < 0 or self.vix < 0:
            raise ValueError("volatility inputs must be non-negative")
        object.__setattr__(self, "regime", MarketRegime(self.regime))
        if not self.algorithm_version.strip():
            raise ValueError("algorithm version is required")
        if not self.source_lineage:
            raise ValueError("market context source lineage is required")


def opinion_to_action(
    opinion: ResearchOpinionValue,
    *,
    current_weight: Decimal,
) -> PortfolioActionValue:
    if not isinstance(current_weight, Decimal):
        raise TypeError("current weight must use Decimal")
    value = ResearchOpinionValue(opinion)
    if value is ResearchOpinionValue.ABSTAIN:
        return PortfolioActionValue.NO_ACTION
    if value is ResearchOpinionValue.BULLISH:
        return PortfolioActionValue.ADD if current_weight > 0 else PortfolioActionValue.ENTER
    if value is ResearchOpinionValue.BEARISH:
        return PortfolioActionValue.EXIT if current_weight > 0 else PortfolioActionValue.NO_ACTION
    return PortfolioActionValue.HOLD


def classify_market_regime(
    *,
    snapshot_id: UUID,
    as_of: datetime,
    available_at: datetime,
    qqq_trend: Decimal,
    qqq_volatility: Decimal,
    soxx_relative_strength: Decimal,
    vix: Decimal,
    algorithm_version: str,
    source_lineage: tuple[UUID, ...],
) -> MarketContextSnapshot:
    timestamp = require_aware(as_of).astimezone(UTC)
    visible_at = require_aware(available_at).astimezone(UTC)
    regime = (
        MarketRegime.RISK_OFF
        if qqq_trend < 0 and soxx_relative_strength < 0 and vix >= Decimal("25")
        else MarketRegime.RISK_ON
        if qqq_trend > 0 and soxx_relative_strength >= 0 and vix < Decimal("25")
        else MarketRegime.MIXED
    )
    return MarketContextSnapshot(
        id=snapshot_id,
        as_of=timestamp,
        available_at=visible_at,
        qqq_trend=qqq_trend,
        qqq_volatility=qqq_volatility,
        soxx_relative_strength=soxx_relative_strength,
        vix=vix,
        regime=regime,
        algorithm_version=algorithm_version,
        source_lineage=source_lineage,
    )
