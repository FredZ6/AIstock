from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from stock_platform.agents.checkpointing import checkpoint_serializer
from stock_platform.agents.harness.budget import BudgetLimits
from stock_platform.agents.harness.task_spec import PolicyVersions, TaskSpecification
from stock_platform.agents.research.graph import DailyResearchGraph
from stock_platform.application.research.persistence import InMemoryResearchStore
from stock_platform.infrastructure.providers.base import FeedType
from stock_platform.infrastructure.providers.fixture.loader import FixtureCatalog


def _specification() -> TaskSpecification:
    now = datetime(2026, 8, 29, tzinfo=UTC)
    return TaskSpecification(
        objective="checkpointed research",
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


def test_research_graph_uses_run_id_as_checkpoint_thread_id() -> None:
    saver = InMemorySaver()
    run_id = "6e1485c8-d3f6-4ef7-8842-32a4751f5873"
    graph = DailyResearchGraph(
        provider=FixtureCatalog.load_default().provider(),
        store=InMemoryResearchStore(),
        checkpointer=saver,
    )

    graph.run(run_id=run_id, specification=_specification())

    checkpoint = saver.get({"configurable": {"thread_id": run_id}})
    assert checkpoint is not None


def test_postgres_checkpoint_factory_rejects_non_postgres_urls() -> None:
    from stock_platform.agents.checkpointing import postgres_checkpointer

    with pytest.raises(ValueError, match="PostgreSQL"):
        with postgres_checkpointer("sqlite:///tmp/checkpoints.db"):
            pass


def test_checkpoint_serializer_uses_an_explicit_constructor_allowlist() -> None:
    serializer = checkpoint_serializer()

    assert serializer._allowed_msgpack_modules is not True


@dataclass
class UntrustedCheckpointValue:
    value: str


def test_checkpoint_serializer_does_not_construct_unlisted_types() -> None:
    encoded = JsonPlusSerializer(allowed_msgpack_modules=True).dumps_typed(
        UntrustedCheckpointValue("unsafe")
    )

    decoded = checkpoint_serializer().loads_typed(encoded)

    assert decoded == {"value": "unsafe"}
    assert not isinstance(decoded, UntrustedCheckpointValue)
