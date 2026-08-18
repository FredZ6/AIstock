from datetime import UTC, datetime

from stock_platform.agents.research.state import append_only
from stock_platform.domain.research.evidence import EvidenceItem


def test_evidence_reducer_is_append_only_and_does_not_mutate_inputs() -> None:
    first = EvidenceItem.from_source(
        symbol="NVDA",
        provider="FIXTURE",
        feed_type="company_facts",
        available_at=datetime(2026, 8, 16, tzinfo=UTC),
        content_hash="a" * 64,
        raw_object_key="m1-v1/sec/nvda-facts.json",
        payload={"revenue": "46000000000"},
    )
    left = (first,)

    combined = append_only(left, (first,))

    assert combined == (first, first)
    assert left == (first,)
