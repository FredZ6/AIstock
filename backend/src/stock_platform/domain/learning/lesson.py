"""Candidate lessons remain inert until replay and explicit human approval."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from stock_platform.domain.common.time import require_aware
from stock_platform.domain.learning.attribution import ErrorCategory


class LessonStatus(StrEnum):
    CANDIDATE = "CANDIDATE"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class CandidateLesson:
    id: UUID
    attribution_id: UUID
    scope: str
    statement: str
    evidence: tuple[str, ...]
    counter_evidence: tuple[str, ...]
    confidence: Decimal
    replay_delta: Decimal
    creator: str
    created_at: datetime
    category: ErrorCategory
    status: LessonStatus = LessonStatus.CANDIDATE

    def __post_init__(self) -> None:
        if not self.scope.strip() or not self.statement.strip() or not self.creator.strip():
            raise ValueError("lesson scope, statement, and creator are required")
        if not self.evidence:
            raise ValueError("lesson evidence is required")
        if not isinstance(self.confidence, Decimal) or not isinstance(self.replay_delta, Decimal):
            raise TypeError("lesson confidence and replay delta must use Decimal")
        if not self.confidence.is_finite() or not Decimal("0") <= self.confidence <= Decimal("1"):
            raise ValueError("lesson confidence must be between zero and one")
        if not self.replay_delta.is_finite():
            raise ValueError("lesson replay delta must be finite")
        object.__setattr__(self, "created_at", require_aware(self.created_at).astimezone(UTC))
        object.__setattr__(self, "category", ErrorCategory(self.category))
        object.__setattr__(self, "status", LessonStatus(self.status))

    @property
    def duplicate_key(self) -> tuple[str, str]:
        return (
            " ".join(self.scope.casefold().split()),
            " ".join(self.statement.casefold().split()),
        )


class LessonBook:
    def __init__(self) -> None:
        self._lessons: dict[tuple[str, str], CandidateLesson] = {}

    def add(self, lesson: CandidateLesson) -> None:
        if lesson.duplicate_key in self._lessons:
            raise ValueError("duplicate candidate lesson")
        self._lessons[lesson.duplicate_key] = lesson
