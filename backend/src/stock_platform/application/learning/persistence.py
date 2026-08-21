"""Transactional persistence for complete weekly-review history."""

from typing import cast
from uuid import UUID

from sqlalchemy import Connection, select
from sqlalchemy.dialects.postgresql import insert

from stock_platform.agents.harness.task_spec import TaskSpecification
from stock_platform.agents.weekly_review.state import WeeklyReviewResult
from stock_platform.infrastructure.db.models.tables import (
    candidate_lesson,
    decision_outcome,
    error_attribution,
    lesson_attribution_link,
    replay_run,
    weekly_review_run,
)


class PostgresWeeklyReviewStore:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def _run_id(
        self, result: WeeklyReviewResult, specification: TaskSpecification
    ) -> tuple[UUID, bool]:
        versions = specification.policy_versions
        decision_ids = {outcome.decision_id for outcome in result.outcomes} | set(
            result.pending_decision_ids
        )
        values = {
            "run_key": result.run_id,
            "decision_ids": sorted(str(decision_id) for decision_id in decision_ids),
            "decision_time": specification.decision_time,
            "data_cutoff": specification.data_cutoff,
            "research_scoring_policy_version": versions.research_scoring,
            "risk_policy_version": versions.risk,
            "execution_policy_version": versions.execution,
            "confidence_policy_version": versions.confidence,
            "prompt_version": versions.prompt,
            "model_version": versions.model,
            "status": "COMPLETED",
        }
        inserted = self.connection.execute(
            insert(weekly_review_run)
            .values(**values)
            .on_conflict_do_nothing(index_elements=[weekly_review_run.c.run_key])
            .returning(weekly_review_run.c.id)
        ).scalar_one_or_none()
        if inserted is not None:
            return cast(UUID, inserted), True
        persisted = (
            self.connection.execute(
                select(weekly_review_run).where(weekly_review_run.c.run_key == result.run_id)
            )
            .mappings()
            .one()
        )
        if any(persisted[key] != value for key, value in values.items()):
            raise ValueError("weekly review run key was reused with different frozen inputs")
        return cast(UUID, persisted["id"]), False

    def persist(self, result: WeeklyReviewResult, *, specification: TaskSpecification) -> None:
        run_id, created = self._run_id(result, specification)
        if not created:
            persisted_decision_ids = set(
                self.connection.execute(
                    select(decision_outcome.c.decision_id).where(
                        decision_outcome.c.weekly_review_run_id == run_id
                    )
                ).scalars()
            )
            result_decision_ids = {outcome.decision_id for outcome in result.outcomes}
            if persisted_decision_ids != result_decision_ids:
                raise ValueError("weekly review run key was reused with a different decision set")
        persisted_outcome_ids: dict[UUID, UUID] = {}
        for outcome in result.outcomes:
            values = {
                "weekly_review_run_id": run_id,
                "decision_id": outcome.decision_id,
                "status": outcome.status,
                "returns": {str(int(key)): str(value) for key, value in outcome.returns.items()},
                "excess_returns": {
                    str(int(key)): str(value) for key, value in outcome.excess_returns.items()
                },
                "maximum_favorable_excursion": outcome.maximum_favorable_excursion,
                "maximum_adverse_excursion": outcome.maximum_adverse_excursion,
                "risk_adjusted_return": outcome.risk_adjusted_return,
                "calibration_error": outcome.calibration_error,
                "computed_at": outcome.computed_at,
            }
            inserted_id = self.connection.execute(
                insert(decision_outcome)
                .values(id=outcome.id, **values)
                .on_conflict_do_nothing(constraint="uq_outcome_run_decision")
                .returning(decision_outcome.c.id)
            ).scalar_one_or_none()
            if inserted_id is None:
                persisted = (
                    self.connection.execute(
                        select(decision_outcome).where(
                            decision_outcome.c.weekly_review_run_id == run_id,
                            decision_outcome.c.decision_id == outcome.decision_id,
                        )
                    )
                    .mappings()
                    .one()
                )
                if any(persisted[key] != value for key, value in values.items()):
                    raise ValueError("semantic outcome retry changed immutable facts")
                inserted_id = persisted["id"]
            persisted_outcome_ids[outcome.id] = cast(UUID, inserted_id)
        persisted_attribution_ids: dict[UUID, UUID] = {}
        for attribution in result.attributions:
            values = {
                "outcome_id": persisted_outcome_ids[attribution.outcome_id],
                "category": attribution.category.value,
                "rationale": attribution.rationale,
                "controllable": attribution.controllable,
            }
            inserted_id = self.connection.execute(
                insert(error_attribution)
                .values(id=attribution.id, **values)
                .on_conflict_do_nothing(constraint="uq_attribution_outcome_category")
                .returning(error_attribution.c.id)
            ).scalar_one_or_none()
            if inserted_id is None:
                persisted = (
                    self.connection.execute(
                        select(error_attribution).where(
                            error_attribution.c.outcome_id == values["outcome_id"],
                            error_attribution.c.category == values["category"],
                        )
                    )
                    .mappings()
                    .one()
                )
                if any(persisted[key] != value for key, value in values.items()):
                    raise ValueError("semantic attribution retry changed immutable facts")
                inserted_id = persisted["id"]
            persisted_attribution_ids[attribution.id] = cast(UUID, inserted_id)
        persisted_lesson_ids: dict[UUID, UUID] = {}
        for lesson in result.lessons:
            duplicate_key = "|".join(lesson.duplicate_key)
            inserted_lesson_id = self.connection.execute(
                insert(candidate_lesson)
                .values(
                    id=lesson.id,
                    attribution_id=persisted_attribution_ids[lesson.attribution_id],
                    scope=lesson.scope,
                    statement=lesson.statement,
                    duplicate_key=duplicate_key,
                    evidence=list(lesson.evidence),
                    counter_evidence=list(lesson.counter_evidence),
                    confidence=lesson.confidence,
                    replay_delta=lesson.replay_delta,
                    creator=lesson.creator,
                    status=lesson.status.value,
                    created_at=lesson.created_at,
                )
                .on_conflict_do_nothing(index_elements=[candidate_lesson.c.duplicate_key])
                .returning(candidate_lesson.c.id)
            ).scalar_one_or_none()
            persisted_lesson_ids[lesson.id] = cast(
                UUID,
                inserted_lesson_id
                or self.connection.execute(
                    select(candidate_lesson.c.id).where(
                        candidate_lesson.c.duplicate_key == duplicate_key
                    )
                ).scalar_one(),
            )
            self.connection.execute(
                insert(lesson_attribution_link)
                .values(
                    lesson_id=persisted_lesson_ids[lesson.id],
                    attribution_id=persisted_attribution_ids[lesson.attribution_id],
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        lesson_attribution_link.c.lesson_id,
                        lesson_attribution_link.c.attribution_id,
                    ]
                )
            )
        for replay in result.replays:
            persisted_lesson_id = persisted_lesson_ids.get(replay.lesson_id)
            if persisted_lesson_id is None:
                persisted_lesson_id = self.connection.execute(
                    select(candidate_lesson.c.id).where(candidate_lesson.c.id == replay.lesson_id)
                ).scalar_one_or_none()
            if persisted_lesson_id is None:
                raise ValueError("forward replay requires an existing candidate lesson")
            values = {
                "lesson_id": persisted_lesson_id,
                "decision_ids": [str(item) for item in replay.decision_ids],
                "baseline_score": replay.baseline_score,
                "candidate_score": replay.candidate_score,
                "delta": replay.delta,
                "data_cutoff": specification.data_cutoff,
            }
            inserted_id = self.connection.execute(
                insert(replay_run)
                .values(id=replay.id, **values)
                .on_conflict_do_nothing(constraint="uq_replay_lesson_cutoff")
                .returning(replay_run.c.id)
            ).scalar_one_or_none()
            if inserted_id is None:
                persisted = (
                    self.connection.execute(
                        select(replay_run).where(
                            replay_run.c.lesson_id == values["lesson_id"],
                            replay_run.c.data_cutoff == values["data_cutoff"],
                        )
                    )
                    .mappings()
                    .one()
                )
                if any(persisted[key] != value for key, value in values.items()):
                    raise ValueError("semantic replay retry changed immutable facts")
