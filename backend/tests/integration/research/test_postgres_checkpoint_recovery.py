from collections import Counter
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.engine import Engine
from stock_platform.agents.checkpointing import postgres_checkpointer
from stock_platform.agents.harness.budget import BudgetLimits
from stock_platform.agents.harness.task_spec import PolicyVersions, TaskSpecification
from stock_platform.agents.research.graph import DailyResearchGraph
from stock_platform.application.research.persistence import InMemoryResearchStore
from stock_platform.infrastructure.providers.base import FeedType, ProviderResponse
from stock_platform.infrastructure.providers.fixture.loader import FixtureCatalog


def specification() -> TaskSpecification:
    now = datetime(2026, 8, 16, tzinfo=UTC)
    return TaskSpecification(
        objective="restart-safe research",
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


class CountingProvider:
    def __init__(self) -> None:
        self.delegate = FixtureCatalog.load_default().provider()
        self.calls: Counter[FeedType] = Counter()

    def fetch(self, feed_type: FeedType, symbol: str, as_of: datetime) -> ProviderResponse:
        self.calls[feed_type] += 1
        return self.delegate.fetch(feed_type, symbol, as_of)


def test_postgres_checkpoint_survives_saver_recreation(engine: Engine) -> None:
    database_url = engine.url.render_as_string(hide_password=False)
    provider = CountingProvider()
    store = InMemoryResearchStore()
    run_id = str(uuid4())
    failed = False

    def inject_failure(node: str) -> None:
        nonlocal failed
        if node == "normalize_freshness_lineage" and not failed:
            failed = True
            raise RuntimeError("injected restart")

    with postgres_checkpointer(database_url) as saver:
        with pytest.raises(RuntimeError, match="injected restart"):
            DailyResearchGraph(
                provider=provider,
                store=store,
                checkpointer=saver,
                on_node_completed=inject_failure,
            ).run(run_id=run_id, specification=specification())

    calls_before_restart = provider.calls.copy()
    with postgres_checkpointer(database_url) as recreated_saver:
        result = DailyResearchGraph(
            provider=provider,
            store=store,
            checkpointer=recreated_saver,
        ).run(run_id=run_id, specification=specification())

    assert result.decision_id is not None
    assert provider.calls[FeedType.COMPANY_FACTS] == calls_before_restart[FeedType.COMPANY_FACTS]
    assert provider.calls[FeedType.PRICE_BARS] == calls_before_restart[FeedType.PRICE_BARS]
    assert store.persist_count == 1
