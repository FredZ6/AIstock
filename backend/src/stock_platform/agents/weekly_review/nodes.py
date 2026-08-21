"""Deterministic nodes used by the bounded weekly-review graph."""

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from stock_platform.application.learning.eligibility import matured_horizons
from stock_platform.application.learning.replay import HistoricalDecision, ReplayRun, replay_lesson
from stock_platform.domain.learning.attribution import (
    ErrorAttribution,
    ErrorCategory,
    attribute_error,
)
from stock_platform.domain.learning.lesson import CandidateLesson, LessonBook
from stock_platform.domain.learning.outcome import (
    DecisionForReview,
    DecisionOutcome,
    PriceObservation,
    compute_outcome,
)


class WeeklyReviewNodes:
    def select_matured(
        self, decisions: tuple[DecisionForReview, ...], *, as_of: datetime
    ) -> tuple[tuple[DecisionForReview, ...], tuple[DecisionForReview, ...]]:
        matured = tuple(item for item in decisions if matured_horizons(item, as_of=as_of))
        pending = tuple(item for item in decisions if not matured_horizons(item, as_of=as_of))
        return matured, pending

    def compute_outcomes(
        self,
        decisions: tuple[DecisionForReview, ...],
        *,
        prices: Mapping[UUID, tuple[PriceObservation, ...]],
        benchmark_prices: tuple[PriceObservation, ...],
        as_of: datetime,
    ) -> tuple[DecisionOutcome, ...]:
        return tuple(
            compute_outcome(
                item,
                prices=prices.get(item.id, ()),
                benchmark_prices=benchmark_prices,
                as_of=as_of,
            )
            for item in decisions
        )

    def attribute_errors(
        self,
        decisions: tuple[DecisionForReview, ...],
        outcomes: tuple[DecisionOutcome, ...],
    ) -> tuple[ErrorAttribution, ...]:
        decision_by_id = {item.id: item for item in decisions}
        results: list[ErrorAttribution] = []
        for outcome in outcomes:
            decision = decision_by_id[outcome.decision_id]
            terminal = outcome.returns[max(outcome.returns)] if outcome.returns else Decimal("0")
            results.append(
                attribute_error(
                    outcome_id=outcome.id,
                    opinion=decision.opinion,
                    realized_return=terminal,
                    data_complete=decision.data_complete,
                    data_fresh=decision.data_fresh,
                    evidence_conflicted=decision.evidence_conflicted,
                )
            )
        return tuple(results)

    def create_candidate_lessons(
        self, attributions: tuple[ErrorAttribution, ...], *, created_at: datetime
    ) -> tuple[CandidateLesson, ...]:
        book = LessonBook()
        lessons: list[CandidateLesson] = []
        grouped: dict[ErrorCategory, list[ErrorAttribution]] = {}
        for attribution in attributions:
            grouped.setdefault(attribution.category, []).append(attribution)
        for category, related in grouped.items():
            attribution = related[0]
            lesson = CandidateLesson(
                id=uuid4(),
                attribution_id=attribution.id,
                scope=f"weekly:{category.value.casefold()}",
                statement=f"Review {category.value} before the next decision",
                evidence=tuple(f"outcome:{item.outcome_id}" for item in related),
                counter_evidence=(),
                confidence=Decimal("0.5"),
                replay_delta=Decimal("0"),
                creator="weekly-review-v1",
                created_at=created_at,
                category=category,
            )
            book.add(lesson)
            lessons.append(lesson)
        return tuple(lessons)

    def reflect(self, attributions: tuple[ErrorAttribution, ...]) -> tuple[str, ...]:
        ordered = sorted(
            attributions,
            key=lambda value: (value.category.value, str(value.id)),
        )
        return tuple(f"{item.category.value}:{item.rationale}" for item in ordered)

    def replay(
        self,
        lessons: tuple[CandidateLesson, ...],
        decisions: tuple[DecisionForReview, ...],
        outcomes: tuple[DecisionOutcome, ...],
        attributions: tuple[ErrorAttribution, ...],
    ) -> tuple[ReplayRun, ...]:
        outcome_by_decision = {item.decision_id: item for item in outcomes}
        attribution_by_outcome = {item.outcome_id: item for item in attributions}
        category_by_decision = {
            outcome.decision_id: attribution_by_outcome[outcome.id].category
            for outcome in outcomes
            if outcome.id in attribution_by_outcome
        }
        return tuple(
            replay_lesson(
                lesson,
                tuple(
                    HistoricalDecision(
                        decision.id,
                        decision.decision_time,
                        (
                            outcome_by_decision[decision.id].returns[
                                max(outcome_by_decision[decision.id].returns)
                            ]
                            if outcome_by_decision[decision.id].returns
                            else Decimal("0")
                        ),
                    )
                    for decision in decisions
                    if decision.id in outcome_by_decision
                    and category_by_decision.get(decision.id) is lesson.category
                ),
            )
            for lesson in lessons
        )
