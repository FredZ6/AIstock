"""Decimal-only numeric and unit verification for material research claims."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from uuid import UUID

from stock_platform.domain.research.claims import Claim
from stock_platform.domain.research.evidence import EvidenceItem


class NumericUnit(StrEnum):
    USD = "USD"
    USD_BILLION = "USD_BILLION"
    RATIO = "RATIO"
    PERCENT = "PERCENT"
    PERCENTAGE_POINT = "PERCENTAGE_POINT"
    COUNT = "COUNT"


class NumericIssueCode(StrEnum):
    VALUE_MISMATCH = "VALUE_MISMATCH"
    UNIT_MISMATCH = "UNIT_MISMATCH"
    SOURCE_MISSING = "SOURCE_MISSING"
    SOURCE_INVALID = "SOURCE_INVALID"


@dataclass(frozen=True, slots=True)
class NumericAssertion:
    reported: Decimal
    expected: Decimal
    reported_unit: NumericUnit
    expected_unit: NumericUnit
    tolerance: Decimal = Decimal("0")
    claim_id: UUID | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.reported, Decimal) or not isinstance(self.expected, Decimal):
            raise TypeError("numeric values must use Decimal")
        if not isinstance(self.tolerance, Decimal):
            raise TypeError("numeric tolerance must use Decimal")
        if self.tolerance < Decimal("0"):
            raise ValueError("numeric tolerance cannot be negative")


@dataclass(frozen=True, slots=True)
class NumericIssue:
    code: NumericIssueCode
    claim_id: UUID | None
    detail: str


@dataclass(frozen=True, slots=True)
class NumericVerification:
    verified: bool
    issues: tuple[NumericIssue, ...]


class NumericVerifier:
    def verify(self, assertions: tuple[NumericAssertion, ...]) -> NumericVerification:
        issues: list[NumericIssue] = []
        for assertion in assertions:
            if assertion.reported_unit is not assertion.expected_unit:
                issues.append(
                    NumericIssue(
                        NumericIssueCode.UNIT_MISMATCH,
                        assertion.claim_id,
                        (
                            f"reported {assertion.reported_unit.value}, expected "
                            f"{assertion.expected_unit.value}"
                        ),
                    )
                )
            elif abs(assertion.reported - assertion.expected) > assertion.tolerance:
                issues.append(
                    NumericIssue(
                        NumericIssueCode.VALUE_MISMATCH,
                        assertion.claim_id,
                        (
                            f"reported {assertion.reported}, expected {assertion.expected}, "
                            f"tolerance {assertion.tolerance}"
                        ),
                    )
                )
        return NumericVerification(verified=not issues, issues=tuple(issues))

    def verify_claims(
        self, claims: tuple[Claim, ...], evidence: tuple[EvidenceItem, ...]
    ) -> NumericVerification:
        evidence_by_id = {item.id: item for item in evidence}
        assertions: list[NumericAssertion] = []
        issues: list[NumericIssue] = []
        for claim in claims:
            if claim.numeric_field is None:
                continue
            item = evidence_by_id.get(claim.evidence_id)
            if item is None or claim.numeric_value is None or claim.numeric_unit is None:
                issues.append(
                    NumericIssue(
                        NumericIssueCode.SOURCE_MISSING,
                        claim.id,
                        "numeric claim is missing its deterministic source",
                    )
                )
                continue
            source = item.payload.get(claim.numeric_field)
            try:
                expected = Decimal(str(source))
                unit = NumericUnit(claim.numeric_unit)
            except (InvalidOperation, TypeError, ValueError):
                issues.append(
                    NumericIssue(
                        NumericIssueCode.SOURCE_INVALID,
                        claim.id,
                        "cited numeric source is not a valid Decimal/unit",
                    )
                )
                continue
            assertions.append(
                NumericAssertion(
                    reported=claim.numeric_value,
                    expected=expected,
                    reported_unit=unit,
                    expected_unit=unit,
                    tolerance=Decimal("0"),
                    claim_id=claim.id,
                )
            )
        verified = self.verify(tuple(assertions))
        combined = tuple(issues) + verified.issues
        return NumericVerification(verified=not combined, issues=combined)
