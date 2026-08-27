"""Immutable inputs and results for deterministic financial concept mapping."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from stock_platform.domain.research.evidence import EvidenceGap, EvidenceGapKind


class MappingStatus(StrEnum):
    EXACT = "EXACT"
    DERIVED = "DERIVED"
    UNMAPPED = "UNMAPPED"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True, slots=True)
class FinancialFactInput:
    taxonomy: str
    concept: str
    value: Decimal
    unit: str
    currency: str | None
    period_start: date
    period_end: date
    accession_number: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal):
            raise TypeError("financial fact value must be Decimal")
        if not self.value.is_finite():
            raise ValueError("financial fact value must be finite")
        if self.period_start > self.period_end:
            raise ValueError("financial fact period_start must not exceed period_end")

    @classmethod
    def from_values(
        cls,
        *,
        taxonomy: str,
        concept: str,
        value: str,
        unit: str,
        currency: str | None,
        period_start: str,
        period_end: str,
        accession_number: str,
    ) -> FinancialFactInput:
        try:
            amount = Decimal(value)
        except InvalidOperation as error:
            raise ValueError("financial fact value is invalid") from error
        return cls(
            taxonomy=taxonomy,
            concept=concept,
            value=amount,
            unit=unit,
            currency=currency,
            period_start=date.fromisoformat(period_start),
            period_end=date.fromisoformat(period_end),
            accession_number=accession_number,
        )


@dataclass(frozen=True, slots=True)
class ConceptMappingResult:
    status: MappingStatus
    canonical_concept: str | None
    value: Decimal
    mapping_version: str
    input_provenance: tuple[tuple[str, str], ...]
    source_facts: tuple[FinancialFactInput, ...]

    def to_evidence_gap(self, *, run_id: str, observed_at: datetime) -> EvidenceGap:
        if self.status not in {MappingStatus.UNMAPPED, MappingStatus.AMBIGUOUS}:
            raise ValueError("only unresolved mappings produce EvidenceGap observations")
        source = self.source_facts[0]
        return EvidenceGap.create(
            run_id=run_id,
            kind=(
                EvidenceGapKind.MISSING
                if self.status is MappingStatus.UNMAPPED
                else EvidenceGapKind.CONFLICTED
            ),
            field=f"{source.taxonomy}:{source.concept}",
            domain="financial_fact_mapping",
            reason=f"deterministic concept mapping status is {self.status.value}",
            provider="SEC",
            observed_at=observed_at,
        )
