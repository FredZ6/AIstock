from datetime import UTC, datetime, timedelta
from uuid import uuid4

from stock_platform.application.research.citation_verifier import (
    CitationIssueCode,
    CitationVerifier,
)
from stock_platform.domain.research.claims import Claim
from stock_platform.domain.research.evidence import EvidenceConflict, EvidenceItem

DECISION_TIME = datetime(2026, 8, 18, 6, tzinfo=UTC)


def evidence(
    *,
    symbol: str = "NVDA",
    feed_type: str = "price_bars",
    available_at: datetime = DECISION_TIME - timedelta(hours=1),
) -> EvidenceItem:
    return EvidenceItem.from_source(
        symbol=symbol,
        provider="FIXTURE",
        feed_type=feed_type,
        available_at=available_at,
        content_hash=(symbol.lower() + "0" * 64)[:64],
        raw_object_key=f"fixture/{symbol.lower()}/{feed_type}.json",
        payload={"close": "196.00"},
    )


def issue_codes(result: object) -> set[CitationIssueCode]:
    return {issue.code for issue in result.issues}  # type: ignore[attr-defined]


def test_material_claim_requires_existing_evidence_for_same_symbol() -> None:
    item = evidence()
    unsupported = Claim.create(
        symbol="NVDA", statement="Unsupported fluent bullish statement", evidence_id=uuid4()
    )
    wrong_symbol = Claim.create(
        symbol="AAPL", statement="Wrong symbol citation", evidence_id=item.id
    )

    result = CitationVerifier().verify(
        claims=(unsupported, wrong_symbol),
        evidence=(item,),
        conflicts=(),
        decision_time=DECISION_TIME,
    )

    assert result.verified is False
    assert issue_codes(result) == {
        CitationIssueCode.UNSUPPORTED,
        CitationIssueCode.WRONG_SYMBOL,
    }


def test_after_cutoff_stale_and_conflicted_citations_fail() -> None:
    future = evidence(available_at=DECISION_TIME + timedelta(seconds=1))
    stale = evidence(
        symbol="AAPL",
        available_at=DECISION_TIME - timedelta(days=4),
    )
    conflict_item = evidence(symbol="MSFT", feed_type="target_consensus")
    claims = tuple(
        Claim.create(symbol=str(item.symbol), statement="Material claim", evidence_id=item.id)
        for item in (future, stale, conflict_item)
    )
    conflict = EvidenceConflict(
        field="median_target",
        evidence_ids=(conflict_item.id,),
        reason="provider target values disagree",
    )

    result = CitationVerifier().verify(
        claims=claims,
        evidence=(future, stale, conflict_item),
        conflicts=(conflict,),
        decision_time=DECISION_TIME,
    )

    assert result.verified is False
    assert issue_codes(result) == {
        CitationIssueCode.AFTER_CUTOFF,
        CitationIssueCode.STALE,
        CitationIssueCode.CONFLICTED,
    }


def test_fresh_supported_claim_passes() -> None:
    item = evidence()
    claim = Claim.create(symbol="NVDA", statement="Supported", evidence_id=item.id)

    result = CitationVerifier().verify(
        claims=(claim,), evidence=(item,), conflicts=(), decision_time=DECISION_TIME
    )

    assert result.verified is True
    assert result.issues == ()
