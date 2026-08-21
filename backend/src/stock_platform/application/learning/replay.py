"""Point-in-time replay that prevents future-lesson leakage."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from stock_platform.domain.common.time import require_aware
from stock_platform.domain.learning.lesson import CandidateLesson


@dataclass(frozen=True, slots=True)
class HistoricalDecision:
    id: UUID
    decision_time: datetime
    score: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_time", require_aware(self.decision_time).astimezone(UTC))
        if not isinstance(self.score, Decimal):
            raise TypeError("historical score must use Decimal")


@dataclass(frozen=True, slots=True)
class ReplayRun:
    id: UUID
    lesson_id: UUID
    decision_ids: tuple[UUID, ...]
    baseline_score: Decimal
    candidate_score: Decimal
    delta: Decimal


def replay_lesson(lesson: CandidateLesson, decisions: tuple[HistoricalDecision, ...]) -> ReplayRun:
    eligible = tuple(item for item in decisions if lesson.created_at < item.decision_time)
    baseline = (
        sum((item.score for item in eligible), Decimal("0")) / Decimal(len(eligible))
        if eligible
        else Decimal("0")
    )
    candidate_score = (
        sum((max(item.score, Decimal("0")) for item in eligible), Decimal("0"))
        / Decimal(len(eligible))
        if eligible
        else baseline
    )
    return ReplayRun(
        id=uuid4(),
        lesson_id=lesson.id,
        decision_ids=tuple(item.id for item in eligible),
        baseline_score=baseline,
        candidate_score=candidate_score,
        delta=candidate_score - baseline,
    )
