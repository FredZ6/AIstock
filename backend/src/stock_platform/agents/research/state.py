"""Typed LangGraph state and append-only reducers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Protocol, TypedDict
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
from stock_platform.infrastructure.providers.base import FeedType, ProviderResponse


def append_only[T](left: tuple[T, ...], right: tuple[T, ...]) -> tuple[T, ...]:
    return tuple(left) + tuple(right)


def merge_responses(
    left: tuple[ProviderResponse, ...], right: tuple[ProviderResponse, ...]
) -> tuple[ProviderResponse, ...]:
    merged = {
        (item.feed_type.value, item.provider, str(item.symbol), item.query_as_of): item
        for item in tuple(left) + tuple(right)
    }
    return tuple(merged[key] for key in sorted(merged))


class HasId(Protocol):
    id: UUID


@dataclass(frozen=True, slots=True)
class ReplaceById[T]:
    """Mark a single-node recomputation that replaces prior fan-in state."""

    values: tuple[T, ...]


def merge_by_id[T: HasId](
    left: tuple[T, ...], right: tuple[T, ...] | ReplaceById[T]
) -> tuple[T, ...]:
    values = right.values if isinstance(right, ReplaceById) else tuple(left) + tuple(right)
    merged = {str(item.id): item for item in values}
    return tuple(merged[key] for key in sorted(merged))


def merge_strings(left: tuple[str, ...], right: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(set(tuple(left) + tuple(right))))


def merge_conflicts(
    left: tuple[EvidenceConflict, ...], right: tuple[EvidenceConflict, ...]
) -> tuple[EvidenceConflict, ...]:
    merged = {
        (item.field, tuple(str(value) for value in item.evidence_ids), item.reason): item
        for item in tuple(left) + tuple(right)
    }
    return tuple(merged[key] for key in sorted(merged))


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
    collection_targets: tuple[FeedType, ...]
    route: Annotated[tuple[str, ...], append_only]
    responses: Annotated[tuple[ProviderResponse, ...], merge_responses]
    evidence: Annotated[tuple[EvidenceItem, ...], merge_by_id]
    claims: Annotated[tuple[Claim, ...], merge_by_id]
    gaps: tuple[EvidenceGap, ...]
    conflicts: tuple[EvidenceConflict, ...]
    warnings: Annotated[tuple[str, ...], merge_strings]
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
            route=tuple(state["route"]),
            evidence=tuple(state["evidence"]),
            claims=tuple(state["claims"]),
            gaps=tuple(state["gaps"]),
            conflicts=tuple(state["conflicts"]),
            warnings=tuple(state["warnings"]),
            reflections=state["reflections"],
            score=state["score"],
            confidence=state["confidence"],
            thesis=state["thesis"],
            opinion=state["opinion"],
            evidence_links=tuple(state["evidence_links"]),
            report=state["report"],
            citations_verified=state["citations_verified"],
            decision_diff=state["decision_diff"],
            decision_id=state["decision_id"],
            specification=state["specification"],
        )
