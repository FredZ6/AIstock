from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from stock_platform.application.ingestion.concept_mapping import ConceptMappingRegistry
from stock_platform.domain.market_data.concepts import (
    FinancialFactInput,
    MappingStatus,
)
from stock_platform.domain.research.evidence import EvidenceGapKind

CONFIG = Path("backend/config/financial_concepts_v1.yaml")
OBSERVED_AT = datetime(2026, 8, 25, tzinfo=UTC)


def _fact(
    taxonomy: str,
    concept: str,
    value: Decimal,
    *,
    unit: str = "USD",
) -> FinancialFactInput:
    return FinancialFactInput(
        taxonomy=taxonomy,
        concept=concept,
        value=value,
        unit=unit,
        currency="USD" if unit == "USD" else None,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 6, 30),
        accession_number="0001045810-26-000042",
    )


@pytest.mark.parametrize(
    ("taxonomy", "concept"),
    [("us-gaap", "Revenues"), ("ifrs-full", "Revenue")],
)
def test_exact_us_gaap_and_ifrs_mappings_are_versioned(
    taxonomy: str,
    concept: str,
) -> None:
    result = ConceptMappingRegistry.load(CONFIG).map_fact(
        _fact(taxonomy, concept, Decimal("44000000000"))
    )

    assert result.status is MappingStatus.EXACT
    assert result.canonical_concept == "REVENUE"
    assert result.value == Decimal("44000000000")
    assert result.mapping_version == "financial-concepts-v1"
    assert result.input_provenance == ((taxonomy, concept),)


def test_derived_free_cash_flow_uses_decimal_and_preserves_both_inputs() -> None:
    registry = ConceptMappingRegistry.load(CONFIG)
    operating_cash = _fact(
        "us-gaap", "NetCashProvidedByUsedInOperatingActivities", Decimal("120.25")
    )
    capital_spend = _fact("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment", Decimal("20.10"))

    result = registry.derive("FREE_CASH_FLOW", (operating_cash, capital_spend))

    assert result.status is MappingStatus.DERIVED
    assert result.value == Decimal("100.15")
    assert result.input_provenance == (
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),
        ("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment"),
    )


@pytest.mark.parametrize(
    ("concept", "status", "gap_kind"),
    [
        ("IssuerSpecificExperimentalMetric", MappingStatus.UNMAPPED, EvidenceGapKind.MISSING),
        (
            "OtherOperatingIncomeExpenseNet",
            MappingStatus.AMBIGUOUS,
            EvidenceGapKind.CONFLICTED,
        ),
    ],
)
def test_unmapped_and_ambiguous_concepts_emit_evidence_gap_compatible_observations(
    concept: str,
    status: MappingStatus,
    gap_kind: EvidenceGapKind,
) -> None:
    result = ConceptMappingRegistry.load(CONFIG).map_fact(_fact("us-gaap", concept, Decimal("1")))

    assert result.status is status
    assert result.canonical_concept is None
    gap = result.to_evidence_gap(run_id="mapping-test", observed_at=OBSERVED_AT)
    assert gap.kind is gap_kind
    assert gap.provider == "SEC"
    assert gap.domain == "financial_fact_mapping"


def test_financial_fact_input_rejects_binary_float() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        _fact("us-gaap", "Revenues", 1.1)  # type: ignore[arg-type]


def test_mapping_loader_rejects_duplicate_exact_source_concepts(tmp_path: Path) -> None:
    invalid = tmp_path / "duplicate.yaml"
    invalid.write_text(
        '{"version":"v1","exact":[{"taxonomy":"us-gaap","concept":"Revenues",'
        '"canonical":"REVENUE"},{"taxonomy":"us-gaap","concept":"Revenues",'
        '"canonical":"NET_INCOME"}],"ambiguous":[],"derived":[]}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate exact mapping"):
        ConceptMappingRegistry.load(invalid)
