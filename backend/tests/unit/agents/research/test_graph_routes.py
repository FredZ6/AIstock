from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from stock_platform.agents.harness.budget import BudgetLimits
from stock_platform.agents.harness.task_spec import PolicyVersions, TaskSpecification
from stock_platform.agents.research.graph import DailyResearchGraph
from stock_platform.agents.research.state import ResearchStatus
from stock_platform.application.research.persistence import InMemoryResearchStore
from stock_platform.domain.common.ids import Symbol
from stock_platform.infrastructure.providers.base import FeedType, ProviderResponse, ProviderStatus
from stock_platform.infrastructure.providers.fixture.loader import FixtureCatalog

AS_OF = datetime(2026, 8, 16, tzinfo=UTC)


def specification(run_id: str = "13aa2003-c231-4b0f-8fbb-ff064a0ca911") -> TaskSpecification:
    del run_id
    return TaskSpecification(
        objective="Produce an evidence-grounded NVDA research decision",
        symbols=("NVDA",),
        decision_time=AS_OF,
        data_cutoff=AS_OF,
        allowed_tools=frozenset(feed.value for feed in FeedType),
        budgets=BudgetLimits(),
        output_schema="research-decision-v1",
        completion_rules=frozenset({"decision_persisted", "citations_verified"}),
        policy_versions=PolicyVersions(
            research_scoring="research-v1",
            risk="risk-v1",
            execution="execution-v1",
            confidence="confidence-v1",
            prompt="prompt-v1",
            model="fixture-model-v1",
        ),
    )


def test_graph_contains_the_v02_canonical_route() -> None:
    graph = DailyResearchGraph(
        provider=FixtureCatalog.load_default().provider(),
        store=InMemoryResearchStore(),
    )

    assert graph.node_names == (
        "preflight",
        "planner",
        "parallel_collection",
        "normalize_freshness_lineage",
        "parallel_analysts",
        "evidence_judge",
        "reflect",
        "deterministic_score_confidence",
        "investment_thesis",
        "research_opinion",
        "writer",
        "citation_verifier",
        "degrade_unverified_decision",
        "decision_diff",
        "persist_decision",
    )


def test_conflict_fixture_reflects_once_and_persists_typed_decision() -> None:
    store = InMemoryResearchStore()
    graph = DailyResearchGraph(provider=FixtureCatalog.load_default().provider(), store=store)

    result = graph.run(
        run_id="13aa2003-c231-4b0f-8fbb-ff064a0ca911",
        specification=specification(),
    )

    assert result.status is ResearchStatus.COMPLETED_WITH_LIMITATIONS
    assert result.reflections == 1
    assert result.route.count("reflect") == 1
    assert result.thesis is not None
    assert not hasattr(result.thesis, "evidence_ids")
    assert result.opinion is not None
    assert result.opinion.value.value == "ABSTAIN"
    assert result.decision_diff is not None
    assert result.evidence_links
    assert any(gap.kind.value == "CONFLICTED" for gap in result.gaps)
    assert len(result.conflicts) == len(
        {(item.field, item.evidence_ids, item.reason) for item in result.conflicts}
    )
    assert all(item.available_at <= AS_OF for item in result.evidence)
    assert store.latest(result.run_id) == result


def test_same_run_id_resumes_idempotently_without_duplicate_persistence() -> None:
    store = InMemoryResearchStore()
    graph = DailyResearchGraph(provider=FixtureCatalog.load_default().provider(), store=store)
    run_id = "13aa2003-c231-4b0f-8fbb-ff064a0ca911"

    first = graph.run(run_id=run_id, specification=specification())
    resumed = graph.run(run_id=run_id, specification=specification())

    assert resumed == first
    assert store.persist_count == 1


def test_cancelled_run_stops_at_preflight_without_persisting_a_decision() -> None:
    store = InMemoryResearchStore()
    graph = DailyResearchGraph(provider=FixtureCatalog.load_default().provider(), store=store)

    result = graph.run(
        run_id="13aa2003-c231-4b0f-8fbb-ff064a0ca912",
        specification=specification(),
        cancelled=True,
    )

    assert result.status is ResearchStatus.CANCELLED
    assert result.route == ("preflight",)
    assert result.decision_id is None
    assert store.persist_count == 0


@dataclass
class EmptyProvider:
    name: str = "EMPTY"

    def fetch(self, feed_type: FeedType, symbol: str, as_of: datetime) -> ProviderResponse:
        return ProviderResponse(
            status=ProviderStatus.NOT_FOUND,
            provider=self.name,
            feed_type=feed_type,
            symbol=Symbol(symbol),
            query_as_of=as_of,
            records=(),
            missingness="MISSING",
        )


def test_missing_provider_data_produces_typed_gaps_and_abstention() -> None:
    graph = DailyResearchGraph(provider=EmptyProvider(), store=InMemoryResearchStore())

    result = graph.run(
        run_id="13aa2003-c231-4b0f-8fbb-ff064a0ca913",
        specification=specification(),
    )

    assert result.status is ResearchStatus.COMPLETED_WITH_LIMITATIONS
    assert result.opinion is not None
    assert result.opinion.value.value == "ABSTAIN"
    assert result.gaps
    assert result.reflections == 1


@dataclass
class DegradedIexProvider:
    name: str = "ALPACA"

    def fetch(self, feed_type: FeedType, symbol: str, as_of: datetime) -> ProviderResponse:
        return ProviderResponse(
            status=ProviderStatus.NOT_FOUND,
            provider=self.name,
            feed_type=feed_type,
            symbol=Symbol(symbol),
            query_as_of=as_of,
            warnings=(
                ("market_data_gap:UNAVAILABLE:SIP entitlement unavailable",)
                if feed_type is FeedType.PRICE_BARS
                else ()
            ),
            missingness="MISSING",
        )


def test_admission_warning_becomes_typed_unavailable_gap_without_fixture_provenance() -> None:
    result = DailyResearchGraph(provider=DegradedIexProvider(), store=InMemoryResearchStore()).run(
        run_id="13aa2003-c231-4b0f-8fbb-ff064a0ca914",
        specification=specification(),
    )

    sip_gaps = [gap for gap in result.gaps if gap.reason == "SIP entitlement unavailable"]
    assert len(sip_gaps) == 1
    assert sip_gaps[0].kind.value == "UNAVAILABLE"
    assert sip_gaps[0].provider == "ALPACA"


class CountingFixtureProvider:
    def __init__(self) -> None:
        self.delegate = FixtureCatalog.load_default().provider()
        self.calls: Counter[FeedType] = Counter()

    def fetch(self, feed_type: FeedType, symbol: str, as_of: datetime) -> ProviderResponse:
        self.calls[feed_type] += 1
        return self.delegate.fetch(feed_type, symbol, as_of)


def test_reflection_refetches_only_the_conflicted_feed_once() -> None:
    provider = CountingFixtureProvider()

    result = DailyResearchGraph(
        provider=provider,
        store=InMemoryResearchStore(),
    ).run(
        run_id="086fd82a-72e8-4f89-a1c2-2ef7bad9ddcf",
        specification=specification(),
    )

    assert result.reflections == 1
    assert provider.calls[FeedType.TARGET_CONSENSUS] == 2
    assert all(
        count == 1
        for feed, count in provider.calls.items()
        if feed is not FeedType.TARGET_CONSENSUS
    )
