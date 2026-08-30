from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from time import sleep

from stock_platform.agents.harness.budget import BudgetLimits
from stock_platform.agents.harness.task_spec import PolicyVersions, TaskSpecification
from stock_platform.agents.research.graph import DailyResearchGraph
from stock_platform.agents.research.nodes import core as research_nodes
from stock_platform.application.research.persistence import InMemoryResearchStore
from stock_platform.infrastructure.providers.base import FeedType, ProviderResponse
from stock_platform.infrastructure.providers.fixture.loader import FixtureCatalog


def specification() -> TaskSpecification:
    now = datetime(2026, 8, 16, tzinfo=UTC)
    return TaskSpecification(
        objective="parallel research",
        symbols=("NVDA",),
        decision_time=now,
        data_cutoff=now,
        allowed_tools=frozenset(feed.value for feed in FeedType),
        budgets=BudgetLimits(),
        output_schema="research-decision-v1",
        completion_rules=frozenset({"decision_persisted", "citations_verified"}),
        policy_versions=PolicyVersions(
            "research-v1",
            "risk-v1",
            "execution-v1",
            "confidence-v1",
            "prompt-v1",
            "fixture-model-v1",
        ),
    )


class OverlapTrackingProvider:
    def __init__(self) -> None:
        self._delegate = FixtureCatalog.load_default().provider()
        self._lock = Lock()
        self._active = 0
        self.max_active = 0

    def fetch(self, feed_type: FeedType, symbol: str, as_of: datetime) -> ProviderResponse:
        with self._lock:
            self._active += 1
            self.max_active = max(self.max_active, self._active)
        sleep(0.03)
        try:
            return self._delegate.fetch(feed_type, symbol, as_of)
        finally:
            with self._lock:
                self._active -= 1


def test_collection_fans_out_and_merges_in_deterministic_feed_order() -> None:
    provider = OverlapTrackingProvider()
    graph = DailyResearchGraph(provider=provider, store=InMemoryResearchStore())

    result = graph.run(
        run_id="992530e7-0a3a-46fe-a1ee-a98b878c21a2",
        specification=specification(),
    )
    replay = DailyResearchGraph(
        provider=FixtureCatalog.load_default().provider(),
        store=InMemoryResearchStore(),
    ).run(
        run_id="2d31129f-e6a7-4d35-a7fe-fac47a633856",
        specification=specification(),
    )

    assert provider.max_active > 1
    assert tuple(item.id for item in result.evidence) == tuple(item.id for item in replay.evidence)
    assert len({item.id for item in result.evidence}) == len(result.evidence)
    assert len({item.id for item in result.claims}) == len(result.claims)


def test_analysts_process_evidence_in_parallel(monkeypatch: object) -> None:
    lock = Lock()
    active = 0
    max_active = 0
    original = research_nodes._claim_for

    def tracked_claim(item: object) -> object:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        sleep(0.03)
        try:
            return original(item)  # type: ignore[arg-type]
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(research_nodes, "_claim_for", tracked_claim)  # type: ignore[attr-defined]
    result = DailyResearchGraph(
        provider=FixtureCatalog.load_default().provider(),
        store=InMemoryResearchStore(),
    ).run(
        run_id="992530e7-0a3a-46fe-a1ee-a98b878c21a3",
        specification=specification(),
    )

    assert max_active > 1
    assert {claim.evidence_id for claim in result.claims} == {item.id for item in result.evidence}
