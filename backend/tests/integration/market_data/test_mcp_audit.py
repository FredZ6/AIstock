from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from stock_platform.infrastructure.db.models.tables import agent_event, agent_run, tool_call
from stock_platform.infrastructure.observability.context import (
    CorrelationContext,
    correlation_scope,
)
from stock_platform.infrastructure.providers.base import FeedType
from stock_platform.infrastructure.providers.fixture.loader import FixtureCatalog
from stock_platform.mcp_servers.common import McpProviderGateway, PostgresMcpAuditSink


def test_mcp_denial_audit_is_append_only_and_contains_no_arguments(engine: Engine) -> None:
    with engine.connect() as connection:
        transaction = connection.begin()
        PostgresMcpAuditSink(connection).record("place_order", "a" * 64, "denied")

        call = connection.execute(
            select(tool_call.c.tool_name, tool_call.c.request_fingerprint).where(
                tool_call.c.request_fingerprint == "a" * 64
            )
        ).one()
        event = connection.execute(
            select(agent_event.c.event_type, agent_event.c.payload).where(
                agent_event.c.payload["request_fingerprint"].astext == "a" * 64
            )
        ).one()
        count = connection.execute(
            select(func.count())
            .select_from(tool_call)
            .where(tool_call.c.request_fingerprint == "a" * 64)
        ).scalar_one()
        transaction.rollback()

    assert call.tool_name == "place_order"
    assert call.request_fingerprint == "a" * 64
    assert event.event_type == "mcp.tool.denied"
    assert event.payload == {
        "tool_name": "place_order",
        "request_fingerprint": "a" * 64,
        "outcome": "denied",
    }
    assert count == 1


def test_mcp_audit_is_attached_to_the_active_run_and_correlation(engine: Engine) -> None:
    run_id = uuid4()
    correlation_id = uuid4()
    fingerprint = "b" * 64
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(
            agent_run.insert().values(
                id=run_id,
                correlation_id=correlation_id,
                run_type="RESEARCH",
                idempotency_key=f"mcp-gateway-{run_id}",
                request_hash="d" * 64,
                request_payload={},
                decision_time=datetime(2026, 8, 23, tzinfo=UTC),
                data_cutoff=datetime(2026, 8, 23, tzinfo=UTC),
            )
        )
        with correlation_scope(CorrelationContext(correlation_id, run_id)):
            PostgresMcpAuditSink(connection).record("get_prices", fingerprint, "completed")
        call = connection.execute(
            select(tool_call.c.run_id, tool_call.c.correlation_id).where(
                tool_call.c.request_fingerprint == fingerprint
            )
        ).one()
        event = connection.execute(
            select(agent_event.c.run_id, agent_event.c.correlation_id).where(
                agent_event.c.payload["request_fingerprint"].astext == fingerprint
            )
        ).one()
        transaction.rollback()

    assert tuple(call) == (run_id, correlation_id)
    assert tuple(event) == (run_id, correlation_id)


def test_graph_provider_gateway_crosses_mcp_audit_boundary(engine: Engine) -> None:
    run_id = uuid4()
    correlation_id = uuid4()
    catalog = FixtureCatalog.load_default()
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(
            agent_run.insert().values(
                id=run_id,
                correlation_id=correlation_id,
                run_type="RESEARCH",
                idempotency_key=f"mcp-gateway-{run_id}",
                request_hash="e" * 64,
                request_payload={},
                decision_time=datetime(2026, 8, 23, tzinfo=UTC),
                data_cutoff=datetime(2026, 8, 23, tzinfo=UTC),
            )
        )
        gateway = McpProviderGateway(catalog.provider(), PostgresMcpAuditSink(connection))
        with correlation_scope(CorrelationContext(correlation_id, run_id)):
            result = gateway.fetch(FeedType.PRICE_BARS, "NVDA", catalog.entries[0].available_at)
        audit = connection.execute(
            select(tool_call.c.run_id, tool_call.c.correlation_id, tool_call.c.tool_name).where(
                tool_call.c.run_id == run_id
            )
        ).one()
        transaction.rollback()

    assert result.provider == "FIXTURE"
    assert tuple(audit) == (run_id, correlation_id, "get_price_bars")
