"""Append-only human decisions for candidate lessons."""

from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import Connection, insert, select

from stock_platform.application.learning.promotion import HumanActor, require_authenticated_human
from stock_platform.infrastructure.db.models.tables import (
    candidate_lesson,
    decision_outcome,
    error_attribution,
    lesson_approval,
)

LessonDecision = Literal["APPROVE", "REJECT"]


class LessonNotFound(LookupError):
    """The requested lesson does not belong to the weekly review."""


def record_lesson_decision(
    connection: Connection,
    *,
    review_id: UUID,
    lesson_id: UUID,
    actor: HumanActor,
    action: LessonDecision,
    rationale: str,
) -> dict[str, Any]:
    require_authenticated_human(actor)
    exists = connection.execute(
        select(candidate_lesson.c.id)
        .join(error_attribution, candidate_lesson.c.attribution_id == error_attribution.c.id)
        .join(decision_outcome, error_attribution.c.outcome_id == decision_outcome.c.id)
        .where(
            candidate_lesson.c.id == lesson_id,
            decision_outcome.c.weekly_review_run_id == review_id,
        )
    ).scalar_one_or_none()
    if exists is None:
        raise LessonNotFound("lesson not found in weekly review")
    return cast(
        dict[str, Any],
        dict(
            connection.execute(
                insert(lesson_approval)
                .values(
                    lesson_id=lesson_id,
                    actor_id=actor.id,
                    action=action,
                    rationale=rationale,
                )
                .returning(lesson_approval)
            )
            .mappings()
            .one()
        ),
    )
