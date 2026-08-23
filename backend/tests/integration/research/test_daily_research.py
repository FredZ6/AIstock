from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from stock_platform.agents.harness.budget import BudgetLimits
from stock_platform.agents.harness.task_spec import PolicyVersions, TaskSpecification
from stock_platform.agents.research.graph import DailyResearchGraph
from stock_platform.application.research.persistence import PostgresResearchStore
from stock_platform.infrastructure.db.models.tables import (
    agent_event,
    claim,
    decision_snapshot,
    derived_metric,
    evidence_item,
    investment_thesis,
    normalized_record,
    raw_data_object,
    thesis_evidence_link,
)
from stock_platform.infrastructure.providers.base import FeedType
from stock_platform.infrastructure.providers.fixture.loader import FixtureCatalog

AS_OF = datetime(2026, 8, 16, tzinfo=UTC)


@pytest.fixture
def research_graph(engine: Engine) -> Iterator[tuple[DailyResearchGraph, PostgresResearchStore]]:
    catalog = FixtureCatalog.load_default()
    with engine.connect() as connection:
        transaction = connection.begin()
        catalog.seed_database(connection)
        store = PostgresResearchStore(connection)
        yield DailyResearchGraph(provider=catalog.provider(), store=store), store
        transaction.rollback()


def test_offline_daily_research_persists_decision_and_complete_lineage(
    research_graph: tuple[DailyResearchGraph, PostgresResearchStore],
) -> None:
    graph, store = research_graph
    run_id = "13aa2003-c231-4b0f-8fbb-ff064a0ca915"
    specification = TaskSpecification(
        objective="Research the frozen NVDA fixture",
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

    result = graph.run(run_id=run_id, specification=specification)

    assert result.decision_id is not None
    assert store.latest(run_id) == result
    connection = store.connection
    lineage = (
        select(
            decision_snapshot.c.id,
            investment_thesis.c.id,
            claim.c.id,
            evidence_item.c.id,
            derived_metric.c.id,
            normalized_record.c.id,
            raw_data_object.c.id,
        )
        .select_from(
            decision_snapshot.join(
                investment_thesis,
                decision_snapshot.c.thesis_id == investment_thesis.c.id,
            )
            .join(
                thesis_evidence_link,
                thesis_evidence_link.c.thesis_id == investment_thesis.c.id,
            )
            .join(evidence_item, evidence_item.c.id == thesis_evidence_link.c.evidence_id)
            .join(claim, claim.c.evidence_id == evidence_item.c.id)
            .join(derived_metric, derived_metric.c.id == evidence_item.c.derived_metric_id)
            .join(
                normalized_record,
                normalized_record.c.id == derived_metric.c.normalized_record_id,
            )
            .join(
                raw_data_object,
                raw_data_object.c.id == normalized_record.c.raw_data_object_id,
            )
        )
        .where(decision_snapshot.c.id == result.decision_id)
    )
    assert connection.execute(lineage).first() is not None
    assert connection.execute(
        select(func.count()).select_from(agent_event).where(agent_event.c.run_id == run_id)
    ).scalar_one() == len(result.route)
    persisted_events = [
        tuple(row)
        for row in connection.execute(
            select(agent_event.c.event_type, agent_event.c.payload)
            .where(agent_event.c.run_id == run_id)
            .order_by(agent_event.c.sequence)
        )
    ]
    assert persisted_events == [
        ("node.completed", {"node": node, "status": result.status.value}) for node in result.route
    ]
    assert set(
        connection.execute(
            select(agent_event.c.correlation_id).where(agent_event.c.run_id == run_id)
        ).scalars()
    ) == {UUID(run_id)}


def test_two_runs_reuse_stable_evidence_without_duplicate_facts(
    research_graph: tuple[DailyResearchGraph, PostgresResearchStore],
) -> None:
    graph, store = research_graph
    specification = TaskSpecification(
        objective="Research the frozen NVDA fixture",
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

    first = graph.run(
        run_id="13aa2003-c231-4b0f-8fbb-ff064a0ca916",
        specification=specification,
    )
    evidence_after_first = store.connection.execute(
        select(func.count())
        .select_from(evidence_item)
        .where(evidence_item.c.id.in_([item.id for item in first.evidence]))
    ).scalar_one()
    second = graph.run(
        run_id="13aa2003-c231-4b0f-8fbb-ff064a0ca917",
        specification=specification,
    )

    assert second.decision_id != first.decision_id
    assert (
        store.connection.execute(
            select(func.count())
            .select_from(evidence_item)
            .where(evidence_item.c.id.in_([item.id for item in first.evidence]))
        ).scalar_one()
        == evidence_after_first
    )
