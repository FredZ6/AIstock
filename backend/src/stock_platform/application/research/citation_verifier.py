"""Deterministic claim support, symbol, cutoff, freshness, and conflict checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from stock_platform.domain.common.time import require_aware
from stock_platform.domain.research.claims import Claim
from stock_platform.domain.research.evidence import EvidenceConflict, EvidenceItem


class CitationIssueCode(StrEnum):
    UNSUPPORTED = "UNSUPPORTED"
    WRONG_SYMBOL = "WRONG_SYMBOL"
    AFTER_CUTOFF = "AFTER_CUTOFF"
    STALE = "STALE"
    CONFLICTED = "CONFLICTED"


@dataclass(frozen=True, slots=True)
class CitationIssue:
    code: CitationIssueCode
    claim_id: UUID
    evidence_id: UUID
    detail: str


@dataclass(frozen=True, slots=True)
class CitationVerification:
    verified: bool
    issues: tuple[CitationIssue, ...]


_DEFAULT_MAX_AGE = {
    "company_facts": timedelta(days=120),
    "filings": timedelta(days=120),
    "filing_sections": timedelta(days=120),
    "price_bars": timedelta(days=3),
    "company_news": timedelta(days=7),
    "option_aggregates": timedelta(days=3),
    "estimates": timedelta(days=30),
    "target_consensus": timedelta(days=30),
}


class CitationVerifier:
    def __init__(self, *, max_age: dict[str, timedelta] | None = None) -> None:
        self._max_age = dict(_DEFAULT_MAX_AGE if max_age is None else max_age)

    def verify(
        self,
        *,
        claims: tuple[Claim, ...],
        evidence: tuple[EvidenceItem, ...],
        conflicts: tuple[EvidenceConflict, ...],
        decision_time: datetime,
    ) -> CitationVerification:
        cutoff = require_aware(decision_time)
        evidence_by_id = {item.id: item for item in evidence}
        conflicted_ids = {
            evidence_id for conflict in conflicts for evidence_id in conflict.evidence_ids
        }
        issues: list[CitationIssue] = []
        for claim in claims:
            if not claim.material:
                continue
            item = evidence_by_id.get(claim.evidence_id)
            if item is None:
                issues.append(
                    CitationIssue(
                        CitationIssueCode.UNSUPPORTED,
                        claim.id,
                        claim.evidence_id,
                        "material claim has no cited evidence",
                    )
                )
                continue
            if item.symbol != claim.symbol:
                issues.append(
                    CitationIssue(
                        CitationIssueCode.WRONG_SYMBOL,
                        claim.id,
                        item.id,
                        f"claim symbol {claim.symbol} does not match evidence {item.symbol}",
                    )
                )
            if item.available_at > cutoff:
                issues.append(
                    CitationIssue(
                        CitationIssueCode.AFTER_CUTOFF,
                        claim.id,
                        item.id,
                        "evidence was not available at decision time",
                    )
                )
            max_age = self._max_age.get(item.feed_type)
            if max_age is not None and cutoff - item.available_at > max_age:
                issues.append(
                    CitationIssue(
                        CitationIssueCode.STALE,
                        claim.id,
                        item.id,
                        f"evidence exceeds freshness limit {max_age}",
                    )
                )
            if item.id in conflicted_ids:
                issues.append(
                    CitationIssue(
                        CitationIssueCode.CONFLICTED,
                        claim.id,
                        item.id,
                        "critical cited evidence remains conflicted",
                    )
                )
        return CitationVerification(verified=not issues, issues=tuple(issues))
