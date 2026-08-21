from decimal import Decimal
from uuid import uuid4

from stock_platform.domain.learning.attribution import ErrorCategory, attribute_error
from stock_platform.domain.research.claims import ResearchOpinionValue


def test_thesis_direction_is_compared_with_realized_outcome() -> None:
    attribution = attribute_error(
        outcome_id=uuid4(),
        opinion=ResearchOpinionValue.BULLISH,
        realized_return=Decimal("-0.15"),
        data_complete=True,
        data_fresh=True,
        evidence_conflicted=False,
    )

    assert attribution.category is ErrorCategory.THESIS_ERROR
    assert attribution.controllable is True


def test_data_and_evidence_errors_take_priority_over_thesis_error() -> None:
    missing = attribute_error(
        outcome_id=uuid4(),
        opinion=ResearchOpinionValue.BULLISH,
        realized_return=Decimal("-0.15"),
        data_complete=False,
        data_fresh=True,
        evidence_conflicted=False,
    )
    conflict = attribute_error(
        outcome_id=uuid4(),
        opinion=ResearchOpinionValue.BULLISH,
        realized_return=Decimal("-0.15"),
        data_complete=True,
        data_fresh=True,
        evidence_conflicted=True,
    )

    assert missing.category is ErrorCategory.MISSING_EVIDENCE
    assert conflict.category is ErrorCategory.CONFLICT_IGNORED


def test_error_taxonomy_is_locked() -> None:
    assert {item.value for item in ErrorCategory} == {
        "STALE_DATA",
        "MISSING_EVIDENCE",
        "FACT_ERROR",
        "CONFLICT_IGNORED",
        "THESIS_ERROR",
        "TIMING_ERROR",
        "POSITION_SIZING_ERROR",
        "EXECUTION_ERROR",
        "REGIME_CHANGE",
        "RISK_POLICY_FAILURE",
        "UNCONTROLLABLE_EVENT",
    }
