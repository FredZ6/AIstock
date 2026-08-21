from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from stock_platform.application.learning.replay import HistoricalDecision, replay_lesson
from stock_platform.domain.learning.attribution import ErrorCategory
from stock_platform.domain.learning.lesson import CandidateLesson

NOW = datetime(2026, 8, 21, tzinfo=UTC)


def candidate(created_at: datetime, *, replay_delta: Decimal = Decimal("0.1")) -> CandidateLesson:
    return CandidateLesson(
        id=uuid4(),
        attribution_id=uuid4(),
        scope="research:fundamentals",
        statement="Require current filings",
        evidence=("outcome:1",),
        counter_evidence=(),
        confidence=Decimal("0.8"),
        replay_delta=replay_delta,
        creator="weekly-review-v1",
        created_at=created_at,
        category=ErrorCategory.MISSING_EVIDENCE,
    )


def test_replay_excludes_candidate_from_its_own_and_earlier_decisions() -> None:
    item = candidate(NOW)
    decisions = (
        HistoricalDecision(uuid4(), NOW - timedelta(days=1), Decimal("-0.1")),
        HistoricalDecision(uuid4(), NOW, Decimal("-0.1")),
        HistoricalDecision(uuid4(), NOW + timedelta(days=1), Decimal("-0.1")),
    )

    replay = replay_lesson(item, decisions)

    assert replay.decision_ids == (decisions[2].id,)


def test_replay_delta_is_computed_by_deterministic_code() -> None:
    item = candidate(NOW - timedelta(days=10), replay_delta=Decimal("0.9"))
    decisions = (
        HistoricalDecision(uuid4(), NOW - timedelta(days=2), Decimal("-0.2")),
        HistoricalDecision(uuid4(), NOW - timedelta(days=1), Decimal("0.1")),
    )

    replay = replay_lesson(item, decisions)

    assert replay.baseline_score == Decimal("-0.05")
    assert replay.candidate_score == Decimal("0.05")
    assert replay.delta == Decimal("0.1")
