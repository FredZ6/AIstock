from pathlib import Path
from typing import Any

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from stock_platform.mcp_servers.analyst_research.server import (
    create_server as create_analyst_server,
)
from stock_platform.mcp_servers.common import AuditOutcome
from stock_platform.mcp_servers.market_research.server import create_server as create_market_server
from stock_platform.mcp_servers.sec_research.server import create_server as create_sec_server

FORBIDDEN_TOOL_NAMES = {
    "place_order",
    "send_notification",
    "modify_policy",
    "execute_sql",
    "run_shell",
    "fetch_url",
}
FORBIDDEN_ARGUMENTS = {"url", "sql", "shell", "command", "api_key", "credentials"}


class RecordingAuditSink:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, AuditOutcome]] = []

    def record(self, tool_name: str, request_fingerprint: str, outcome: AuditOutcome) -> None:
        self.events.append((tool_name, request_fingerprint, outcome))


async def all_tools() -> dict[str, Any]:
    tools: dict[str, Any] = {}
    for factory in (create_sec_server, create_market_server, create_analyst_server):
        tools.update({tool.name: tool for tool in await factory().list_tools()})
    return tools


@pytest.mark.anyio
async def test_forbidden_capabilities_are_not_registered_or_accepted() -> None:
    tools = await all_tools()
    assert not FORBIDDEN_TOOL_NAMES.intersection(tools)
    for tool in tools.values():
        assert not FORBIDDEN_ARGUMENTS.intersection(tool.inputSchema["properties"])
        assert tool.inputSchema["additionalProperties"] is False

    audit = RecordingAuditSink()
    market = create_market_server(audit_sink=audit)
    with pytest.raises(ToolError, match="Unknown tool"):
        await market.call_tool("place_order", {"symbol": "NVDA"})
    with pytest.raises(ToolError, match="Extra inputs are not permitted"):
        await market.call_tool(
            "get_price_bars",
            {
                "symbol": "NVDA",
                "as_of": "2026-08-16T12:00:00Z",
                "url": "https://attacker.invalid",
            },
        )
    assert [event[2] for event in audit.events] == ["denied", "denied"]
    assert [event[0] for event in audit.events] == ["place_order", "get_price_bars"]
    assert all(len(event[1]) == 64 for event in audit.events)


def test_tool_bodies_do_not_import_provider_sdks() -> None:
    root = Path(__file__).parents[3] / "backend" / "src" / "stock_platform" / "mcp_servers"
    for path in root.glob("*_research/server.py"):
        source = path.read_text(encoding="utf-8")
        assert "infrastructure.providers" not in source
        assert "urllib" not in source
        assert "requests" not in source
