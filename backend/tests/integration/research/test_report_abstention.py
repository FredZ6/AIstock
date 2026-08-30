import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from stock_platform.agents.harness.budget import BudgetLimits
from stock_platform.agents.harness.task_spec import PolicyVersions, TaskSpecification
from stock_platform.agents.research.graph import DailyResearchGraph
from stock_platform.agents.research.nodes import core as research_nodes
from stock_platform.agents.research.state import ResearchStatus
from stock_platform.application.research.citation_verifier import CitationVerifier
from stock_platform.application.research.numeric_verifier import NumericVerifier
from stock_platform.application.research.persistence import InMemoryResearchStore
from stock_platform.application.research.report_renderer import ReportRenderer
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.research.claims import (
    Claim,
    InvestmentThesis,
    ResearchOpinion,
    ResearchOpinionValue,
)
from stock_platform.infrastructure.providers.base import FeedType, ProviderResponse
from stock_platform.infrastructure.providers.fixture.loader import FixtureCatalog

AS_OF = datetime(2026, 8, 16, tzinfo=UTC)


def task() -> TaskSpecification:
    return TaskSpecification(
        objective="Research NVDA",
        symbols=("NVDA",),
        decision_time=AS_OF,
        data_cutoff=AS_OF,
        allowed_tools=frozenset(feed.value for feed in FeedType),
        budgets=BudgetLimits(),
        output_schema="research-decision-v1",
        completion_rules=frozenset({"decision_persisted", "citations_verified"}),
        policy_versions=PolicyVersions(
            "research-v1", "risk-v1", "execution-v1", "confidence-v1", "prompt-v1", "fixture-v1"
        ),
    )


def test_conflicted_critical_evidence_forces_abstention_and_complete_report() -> None:
    result = DailyResearchGraph(
        provider=FixtureCatalog.load_default().provider(),
        store=InMemoryResearchStore(),
    ).run(
        run_id="13aa2003-c231-4b0f-8fbb-ff064a0ca918",
        specification=task(),
    )

    assert result.status is ResearchStatus.COMPLETED_WITH_LIMITATIONS
    assert result.opinion is not None
    assert result.opinion.value is ResearchOpinionValue.ABSTAIN
    assert result.citations_verified is False
    report = json.loads(result.report or "{}")
    assert report["research_opinion"] == "ABSTAIN"
    assert report["supporting_evidence"]
    assert report["counter_evidence"]
    assert report["uncertainty"]["gaps"]
    assert report["thesis"]["invalidation_conditions"]
    assert report["decision_diff"]
    assert report["policy_versions"]["confidence"] == "confidence-v1"
    assert (
        report["product_boundary"] == "research signal for a paper portfolio; not investment advice"
    )


def test_unsupported_fluent_bullish_report_is_forced_to_abstain() -> None:
    thesis_id = uuid4()
    thesis = InvestmentThesis(
        id=thesis_id,
        run_id=uuid4(),
        symbol=Symbol("NVDA"),
        as_of=AS_OF,
        direction="BULLISH",
        summary="Fluent but unsupported bullish prose",
        catalysts=("Uncited catalyst",),
        risks=("Unknown",),
        invalidation_conditions=("Missing evidence remains unresolved",),
        horizon="20_TRADING_DAYS",
        confidence=Decimal("0.90"),
        confidence_policy_version="confidence-v1",
        supersedes_thesis_id=None,
        created_at=AS_OF,
    )
    opinion = ResearchOpinion(uuid4(), thesis_id, ResearchOpinionValue.BULLISH)
    unsupported = Claim.create(
        symbol="NVDA", statement="Revenue will accelerate", evidence_id=uuid4()
    )
    citations = CitationVerifier().verify(
        claims=(unsupported,), evidence=(), conflicts=(), decision_time=AS_OF
    )

    rendered = ReportRenderer().render(
        thesis=thesis,
        opinion=opinion,
        claims=(unsupported,),
        evidence=(),
        links=(),
        gaps=(),
        citation_verification=citations,
        numeric_verification=NumericVerifier().verify(()),
        decision_diff={},
        policy_versions=task().policy_versions,
        data_cutoff=AS_OF,
    )

    assert rendered.opinion.value is ResearchOpinionValue.ABSTAIN
    assert json.loads(rendered.content)["research_opinion"] == "ABSTAIN"


class ConflictFreeFixtureProvider:
    def __init__(self) -> None:
        self._delegate = FixtureCatalog.load_default().provider()

    def fetch(self, feed_type: FeedType, symbol: str, as_of: datetime) -> ProviderResponse:
        response = self._delegate.fetch(feed_type, symbol, as_of)
        if feed_type is not FeedType.TARGET_CONSENSUS:
            return response
        return replace(
            response,
            records=tuple(
                replace(record, payload={**record.payload, "median_target": "160"})
                for record in response.records
            ),
        )


def test_numeric_mismatch_alone_downgrades_an_otherwise_cited_decision(
    monkeypatch: object,
) -> None:
    original = research_nodes._claim_for

    def mismatched_claim(item: object) -> Claim:
        claim = original(item)  # type: ignore[arg-type]
        if claim.numeric_value is None:
            return claim
        return replace(claim, numeric_value=claim.numeric_value + Decimal("1"))

    monkeypatch.setattr(research_nodes, "_claim_for", mismatched_claim)  # type: ignore[attr-defined]
    result = DailyResearchGraph(
        provider=ConflictFreeFixtureProvider(),
        store=InMemoryResearchStore(),
    ).run(
        run_id="13aa2003-c231-4b0f-8fbb-ff064a0ca919",
        specification=task(),
    )

    assert result.opinion is not None
    assert result.opinion.value is ResearchOpinionValue.ABSTAIN
    assert "numeric:VALUE_MISMATCH" in result.warnings
    assert not any(warning.startswith("citation:") for warning in result.warnings)
