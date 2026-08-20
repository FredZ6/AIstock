from datetime import UTC, datetime
from decimal import Decimal

import pytest
from stock_platform.application.research.numeric_verifier import (
    NumericAssertion,
    NumericIssueCode,
    NumericUnit,
    NumericVerifier,
)
from stock_platform.domain.research.claims import Claim
from stock_platform.domain.research.evidence import EvidenceItem


def test_numeric_assertion_rejects_binary_float() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        NumericAssertion(
            reported=0.1,  # type: ignore[arg-type]
            expected=Decimal("0.1"),
            reported_unit=NumericUnit.RATIO,
            expected_unit=NumericUnit.RATIO,
        )


def test_declared_decimal_tolerance_controls_financial_rounding() -> None:
    verifier = NumericVerifier()
    within = NumericAssertion(
        reported=Decimal("46.0"),
        expected=Decimal("46.04"),
        reported_unit=NumericUnit.USD_BILLION,
        expected_unit=NumericUnit.USD_BILLION,
        tolerance=Decimal("0.05"),
    )
    outside = NumericAssertion(
        reported=Decimal("46.0"),
        expected=Decimal("46.06"),
        reported_unit=NumericUnit.USD_BILLION,
        expected_unit=NumericUnit.USD_BILLION,
        tolerance=Decimal("0.05"),
    )

    assert verifier.verify((within,)).verified is True
    result = verifier.verify((outside,))
    assert result.verified is False
    assert result.issues[0].code is NumericIssueCode.VALUE_MISMATCH


def test_percent_and_percentage_points_are_not_interchangeable() -> None:
    assertion = NumericAssertion(
        reported=Decimal("5"),
        expected=Decimal("5"),
        reported_unit=NumericUnit.PERCENT,
        expected_unit=NumericUnit.PERCENTAGE_POINT,
    )

    result = NumericVerifier().verify((assertion,))

    assert result.verified is False
    assert result.issues[0].code is NumericIssueCode.UNIT_MISMATCH


def test_numeric_claim_is_recomputed_from_cited_evidence() -> None:
    item = EvidenceItem.from_source(
        symbol="NVDA",
        provider="FIXTURE",
        feed_type="company_facts",
        available_at=datetime(2026, 8, 18, tzinfo=UTC),
        content_hash="a" * 64,
        raw_object_key="fixture/nvda-facts.json",
        payload={"revenue": "46000000000"},
    )
    claim = Claim.create(
        symbol="NVDA",
        statement="Revenue was 46 billion USD",
        evidence_id=item.id,
        numeric_field="revenue",
        numeric_value=Decimal("46000000000"),
        numeric_unit=NumericUnit.USD.value,
    )

    result = NumericVerifier().verify_claims((claim,), (item,))

    assert result.verified is True
