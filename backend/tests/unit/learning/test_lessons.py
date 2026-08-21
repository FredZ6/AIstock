from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from stock_platform.domain.learning.attribution import ErrorCategory
from stock_platform.domain.learning.lesson import CandidateLesson, LessonBook, LessonStatus

NOW = datetime(2026, 8, 21, tzinfo=UTC)


def lesson(text: str = "Require current filings before a bullish call") -> CandidateLesson:
    return CandidateLesson(
        id=uuid4(),
        attribution_id=uuid4(),
        scope="research:fundamentals",
        statement=text,
        evidence=("outcome:1",),
        counter_evidence=("outcome:2",),
        confidence=Decimal("0.75"),
        replay_delta=Decimal("0.08"),
        creator="weekly-review-v1",
        created_at=NOW,
        category=ErrorCategory.MISSING_EVIDENCE,
    )


def test_duplicate_lessons_are_rejected_by_normalized_scope_and_statement() -> None:
    book = LessonBook()
    book.add(lesson())

    with pytest.raises(ValueError, match="duplicate"):
        book.add(lesson("  require CURRENT filings before a bullish call "))


def test_candidate_lesson_retains_auditable_facts() -> None:
    candidate = lesson()

    assert candidate.status is LessonStatus.CANDIDATE
    assert candidate.evidence and candidate.counter_evidence
    assert isinstance(candidate.confidence, Decimal)
    assert isinstance(candidate.replay_delta, Decimal)
