"""Typed claims, theses, and research opinions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid5

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware

_RESEARCH_NAMESPACE = UUID("2c741944-78d2-4e83-8fbd-285675eff0d0")


class ResearchOpinionValue(StrEnum):
    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"
    ABSTAIN = "ABSTAIN"


@dataclass(frozen=True, slots=True)
class Claim:
    id: UUID
    symbol: Symbol
    statement: str
    evidence_id: UUID
    material: bool = True

    @classmethod
    def create(
        cls, *, symbol: str, statement: str, evidence_id: UUID, material: bool = True
    ) -> Claim:
        return cls(
            id=uuid5(_RESEARCH_NAMESPACE, f"{symbol}:{evidence_id}:{statement}"),
            symbol=Symbol(symbol),
            statement=statement,
            evidence_id=evidence_id,
            material=material,
        )


@dataclass(frozen=True, slots=True)
class InvestmentThesis:
    id: UUID
    run_id: UUID
    symbol: Symbol
    as_of: datetime
    direction: str
    summary: str
    catalysts: tuple[str, ...]
    risks: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    horizon: str
    confidence: Decimal
    confidence_policy_version: str
    supersedes_thesis_id: UUID | None
    created_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.as_of)
        require_aware(self.created_at)
        if not Decimal("0") <= self.confidence <= Decimal("1"):
            raise ValueError("confidence must be between zero and one")


@dataclass(frozen=True, slots=True)
class ResearchOpinion:
    id: UUID
    thesis_id: UUID
    value: ResearchOpinionValue


def stable_research_id(run_id: str, kind: str) -> UUID:
    return uuid5(_RESEARCH_NAMESPACE, f"{run_id}:{kind}")
