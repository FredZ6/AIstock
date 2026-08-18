"""Versioned deterministic research score and confidence formulas."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from stock_platform.domain.research.evidence import EvidenceConflict, EvidenceGap, EvidenceItem


@dataclass(frozen=True, slots=True)
class ResearchScore:
    value: Decimal
    policy_version: str


@dataclass(frozen=True, slots=True)
class ConfidenceScore:
    value: Decimal
    policy_version: str


def deterministic_scores(
    *,
    evidence: tuple[EvidenceItem, ...],
    gaps: tuple[EvidenceGap, ...],
    conflicts: tuple[EvidenceConflict, ...],
    scoring_version: str,
    confidence_version: str,
) -> tuple[ResearchScore, ConfidenceScore]:
    if not evidence:
        return (
            ResearchScore(Decimal("0.00"), scoring_version),
            ConfidenceScore(Decimal("0.00"), confidence_version),
        )
    positive = sum(
        1 for item in evidence if item.feed_type in {"company_facts", "price_bars", "company_news"}
    )
    score = (Decimal(positive) / Decimal(len(evidence))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    penalty = Decimal(len(gaps) + len(conflicts)) * Decimal("0.10")
    confidence = max(Decimal("0.00"), min(Decimal("1.00"), Decimal("0.80") - penalty))
    return ResearchScore(score, scoring_version), ConfidenceScore(
        confidence.quantize(Decimal("0.01")), confidence_version
    )
