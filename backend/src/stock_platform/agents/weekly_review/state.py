"""Typed inputs and immutable result for a weekly review run."""

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from stock_platform.application.learning.replay import ReplayRun
from stock_platform.domain.learning.attribution import ErrorAttribution
from stock_platform.domain.learning.lesson import CandidateLesson
from stock_platform.domain.learning.outcome import DecisionOutcome, PriceObservation


@dataclass(frozen=True, slots=True)
class WeeklyReviewResult:
    run_id: str
    route: tuple[str, ...]
    outcomes: tuple[DecisionOutcome, ...]
    pending_decision_ids: tuple[UUID, ...]
    attributions: tuple[ErrorAttribution, ...]
    reflections: tuple[str, ...]
    lessons: tuple[CandidateLesson, ...]
    replays: tuple[ReplayRun, ...]
    checkpoints: tuple[str, ...]


PriceMap = Mapping[UUID, tuple[PriceObservation, ...]]
