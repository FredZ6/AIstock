"""Bounded weekly outcome attribution and controlled-learning workflow."""

from collections.abc import Mapping, Sequence
from datetime import timedelta
from uuid import UUID

from stock_platform.agents.harness.checkpoint import InMemoryCheckpointStore
from stock_platform.agents.harness.task_spec import TaskSpecification
from stock_platform.agents.weekly_review.nodes import WeeklyReviewNodes
from stock_platform.agents.weekly_review.state import WeeklyReviewResult
from stock_platform.domain.learning.lesson import CandidateLesson
from stock_platform.domain.learning.outcome import DecisionForReview, PriceObservation


class WeeklyReviewGraph:
    route = (
        "select_matured",
        "compute_outcomes",
        "attribute_errors",
        "reflect",
        "create_candidate_lessons",
        "replay",
    )

    def __init__(self, *, checkpoints: InMemoryCheckpointStore | None = None) -> None:
        self._nodes = WeeklyReviewNodes()
        self._checkpoints = checkpoints or InMemoryCheckpointStore()

    def run(
        self,
        *,
        run_id: str,
        specification: TaskSpecification,
        decisions: Sequence[DecisionForReview],
        prices: Mapping[UUID, tuple[PriceObservation, ...]],
        benchmark_prices: Sequence[PriceObservation],
        replay_candidates: Sequence[CandidateLesson] = (),
    ) -> WeeklyReviewResult:
        budgets = specification.budgets
        if budgets.llm_calls > 8 or budgets.tool_calls > 8:
            raise ValueError("weekly review allows at most eight LLM and eight tool calls")
        if budgets.reflections != 1:
            raise ValueError("weekly review requires exactly one reflection")
        if budgets.wall_time > timedelta(minutes=10):
            raise ValueError("weekly review wall time cannot exceed ten minutes")
        frozen_decisions = tuple(decisions)
        matured, pending = self._nodes.select_matured(
            frozen_decisions, as_of=specification.data_cutoff
        )
        outcomes = self._nodes.compute_outcomes(
            matured,
            prices=dict(prices),
            benchmark_prices=tuple(benchmark_prices),
            as_of=specification.data_cutoff,
        )
        self._checkpoints.save(
            run_id,
            {
                "stage": "weekly_outcome",
                "outcome_ids": tuple(str(item.id) for item in outcomes),
                "pending_decision_ids": tuple(str(item.id) for item in pending),
            },
            saved_at=specification.decision_time,
        )
        attributions = self._nodes.attribute_errors(matured, outcomes)
        reflections = self._nodes.reflect(attributions)
        lessons = self._nodes.create_candidate_lessons(
            attributions, created_at=specification.decision_time
        )
        replays = self._nodes.replay(
            tuple(replay_candidates), frozen_decisions, outcomes, attributions
        )
        return WeeklyReviewResult(
            run_id=run_id,
            route=self.route,
            outcomes=outcomes,
            pending_decision_ids=tuple(item.id for item in pending),
            attributions=attributions,
            reflections=reflections,
            lessons=lessons,
            replays=replays,
            checkpoints=("weekly_outcome",),
        )
