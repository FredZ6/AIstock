"""Typed LangGraph state and append-only reducers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, TypedDict
from uuid import UUID

from stock_platform.agents.harness.task_spec import TaskSpecification
from stock_platform.domain.research.claims import Claim, InvestmentThesis, ResearchOpinion
from stock_platform.domain.research.evidence import (
    EvidenceConflict,
    EvidenceGap,
    EvidenceItem,
    ThesisEvidenceLink,
)
from stock_platform.domain.research.scores import ConfidenceScore, ResearchScore
from stock_platform.infrastructure.providers.base import ProviderResponse


def append_only[T](left: tuple[T, ...], right: tuple[T, ...]) -> tuple[T, ...]:
    return left + right


class ResearchStatus(StrEnum):
    RUNNING = "RUNNING"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_LIMITATIONS = "COMPLETED_WITH_LIMITATIONS"


class ResearchState(TypedDict):
    run_id: str
    specification: TaskSpecification
    status: ResearchStatus
    cancelled: bool
    route: Annotated[tuple[str, ...], append_only]
    responses: Annotated[tuple[ProviderResponse, ...], append_only]
    evidence: Annotated[tuple[EvidenceItem, ...], append_only]
    claims: Annotated[tuple[Claim, ...], append_only]
    gaps: Annotated[tuple[EvidenceGap, ...], append_only]
    conflicts: Annotated[tuple[EvidenceConflict, ...], append_only]
    warnings: Annotated[tuple[str, ...], append_only]
    reflections: int
    score: ResearchScore | None
    confidence: ConfidenceScore | None
    thesis: InvestmentThesis | None
    opinion: ResearchOpinion | None
    evidence_links: tuple[ThesisEvidenceLink, ...]
    report: str | None
    citations_verified: bool
    decision_diff: Mapping[str, object] | None
    decision_id: UUID | None


@dataclass(frozen=True, slots=True)
class ResearchResult:
    run_id: str
    status: ResearchStatus
    route: tuple[str, ...]
    evidence: tuple[EvidenceItem, ...]
    claims: tuple[Claim, ...]
    gaps: tuple[EvidenceGap, ...]
    conflicts: tuple[EvidenceConflict, ...]
    warnings: tuple[str, ...]
    reflections: int
    score: ResearchScore | None
    confidence: ConfidenceScore | None
    thesis: InvestmentThesis | None
    opinion: ResearchOpinion | None
    evidence_links: tuple[ThesisEvidenceLink, ...]
    report: str | None
    citations_verified: bool
    decision_diff: Mapping[str, object] | None
    decision_id: UUID | None
    specification: TaskSpecification

    @classmethod
    def from_state(cls, state: ResearchState) -> ResearchResult:
        return cls(
            run_id=state["run_id"],
            status=state["status"],
            route=state["route"],
            evidence=state["evidence"],
            claims=state["claims"],
            gaps=state["gaps"],
            conflicts=state["conflicts"],
            warnings=state["warnings"],
            reflections=state["reflections"],
            score=state["score"],
            confidence=state["confidence"],
            thesis=state["thesis"],
            opinion=state["opinion"],
            evidence_links=state["evidence_links"],
            report=state["report"],
            citations_verified=state["citations_verified"],
            decision_diff=state["decision_diff"],
            decision_id=state["decision_id"],
            specification=state["specification"],
        )
