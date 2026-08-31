from datetime import UTC, datetime

import pytest
from stock_platform.domain.research.evidence import EvidenceItem


def test_evidence_payload_rejects_in_place_union_mutation() -> None:
    item = EvidenceItem.from_source(
        symbol="NVDA",
        provider="FIXTURE",
        feed_type="company_facts",
        available_at=datetime(2026, 8, 18, tzinfo=UTC),
        content_hash="a" * 64,
        raw_object_key="fixture/nvda-facts.json",
        payload={"revenue": "46000000000"},
    )
    payload = item.payload

    with pytest.raises(TypeError, match="immutable"):
        payload |= {"revenue": "0"}  # type: ignore[operator]

    assert item.payload["revenue"] == "46000000000"
