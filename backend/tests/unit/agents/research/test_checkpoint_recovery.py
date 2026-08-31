from collections import Counter
from datetime import datetime

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from stock_platform.agents.research.graph import DailyResearchGraph
from stock_platform.application.research.persistence import InMemoryResearchStore
from stock_platform.infrastructure.providers.base import FeedType, ProviderResponse
from stock_platform.infrastructure.providers.fixture.loader import FixtureCatalog
from test_graph_routes import specification


class CountingProvider:
    def __init__(self) -> None:
        self.delegate = FixtureCatalog.load_default().provider()
        self.calls: Counter[FeedType] = Counter()

    def fetch(self, feed_type: FeedType, symbol: str, as_of: datetime) -> ProviderResponse:
        self.calls[feed_type] += 1
        return self.delegate.fetch(feed_type, symbol, as_of)


def test_failed_graph_resumes_without_repeating_checkpointed_collection() -> None:
    saver = InMemorySaver()
    provider = CountingProvider()
    store = InMemoryResearchStore()
    run_id = "739a1085-e286-45a1-81e8-bb71e2bc635c"
    failed_once = False

    def fail_after_collection(node: str) -> None:
        nonlocal failed_once
        if node == "normalize_freshness_lineage" and not failed_once:
            failed_once = True
            raise RuntimeError("injected normalization failure")

    with pytest.raises(RuntimeError, match="injected normalization failure"):
        DailyResearchGraph(
            provider=provider,
            store=store,
            checkpointer=saver,
            on_node_completed=fail_after_collection,
        ).run(run_id=run_id, specification=specification())

    calls_after_failure = provider.calls.copy()
    result = DailyResearchGraph(
        provider=provider,
        store=store,
        checkpointer=saver,
    ).run(run_id=run_id, specification=specification())

    assert result.decision_id is not None
    assert provider.calls[FeedType.COMPANY_FACTS] == calls_after_failure[FeedType.COMPANY_FACTS]
    assert provider.calls[FeedType.PRICE_BARS] == calls_after_failure[FeedType.PRICE_BARS]
    assert store.persist_count == 1


def test_completed_checkpoint_replays_result_into_new_idempotent_store() -> None:
    saver = InMemorySaver()
    provider = CountingProvider()
    run_id = "3b1553ac-c9a9-45ee-b682-e6f76ab83001"
    first_store = InMemoryResearchStore()
    first = DailyResearchGraph(
        provider=provider,
        store=first_store,
        checkpointer=saver,
    ).run(run_id=run_id, specification=specification())
    calls_after_completion = provider.calls.copy()
    recreated_store = InMemoryResearchStore()

    replay = DailyResearchGraph(
        provider=provider,
        store=recreated_store,
        checkpointer=saver,
    ).run(run_id=run_id, specification=specification())

    assert replay.decision_id == first.decision_id
    assert provider.calls == calls_after_completion
    assert recreated_store.persist_count == 1
