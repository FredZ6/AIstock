"""Stable, structured error attribution for matured outcomes."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from stock_platform.domain.research.claims import ResearchOpinionValue


class ErrorCategory(StrEnum):
    STALE_DATA = "STALE_DATA"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    FACT_ERROR = "FACT_ERROR"
    CONFLICT_IGNORED = "CONFLICT_IGNORED"
    THESIS_ERROR = "THESIS_ERROR"
    TIMING_ERROR = "TIMING_ERROR"
    POSITION_SIZING_ERROR = "POSITION_SIZING_ERROR"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    REGIME_CHANGE = "REGIME_CHANGE"
    RISK_POLICY_FAILURE = "RISK_POLICY_FAILURE"
    UNCONTROLLABLE_EVENT = "UNCONTROLLABLE_EVENT"


@dataclass(frozen=True, slots=True)
class ErrorAttribution:
    id: UUID
    outcome_id: UUID
    category: ErrorCategory
    rationale: str
    controllable: bool


def attribute_error(
    *,
    outcome_id: UUID,
    opinion: ResearchOpinionValue,
    realized_return: Decimal,
    data_complete: bool,
    data_fresh: bool,
    evidence_conflicted: bool,
) -> ErrorAttribution:
    if not isinstance(realized_return, Decimal):
        raise TypeError("realized return must use Decimal")
    if not data_complete:
        category, rationale = ErrorCategory.MISSING_EVIDENCE, "required evidence was missing"
    elif not data_fresh:
        category, rationale = ErrorCategory.STALE_DATA, "decision used stale data"
    elif evidence_conflicted:
        category, rationale = ErrorCategory.CONFLICT_IGNORED, "conflicting evidence was ignored"
    elif (opinion is ResearchOpinionValue.BULLISH and realized_return < 0) or (
        opinion is ResearchOpinionValue.BEARISH and realized_return > 0
    ):
        category, rationale = ErrorCategory.THESIS_ERROR, "thesis direction opposed realized return"
    else:
        category, rationale = (
            ErrorCategory.UNCONTROLLABLE_EVENT,
            "no controllable error identified",
        )
    return ErrorAttribution(
        id=uuid4(),
        outcome_id=outcome_id,
        category=category,
        rationale=rationale,
        controllable=category is not ErrorCategory.UNCONTROLLABLE_EVENT,
    )
