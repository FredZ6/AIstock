from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from stock_platform.infrastructure.db.models.tables import agent_event, tool_call
from stock_platform.mcp_servers.common import PostgresMcpAuditSink


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
