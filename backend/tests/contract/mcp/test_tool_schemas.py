import json
from pathlib import Path
from typing import Any

import pytest

from mcp_servers.analyst_research.server import create_server as create_analyst_server
from mcp_servers.market_research.server import create_server as create_market_server
from mcp_servers.sec_research.server import create_server as create_sec_server

CONTRACT_ROOT = Path(__file__).parents[4] / "contracts" / "mcp"
EXPECTED_TOOLS = {
    "sec": {"get_company_facts", "get_filings", "get_filing_sections"},
    "market": {"get_price_bars", "get_company_news", "get_option_aggregates"},
    "analyst": {"get_estimates", "get_target_consensus"},
}
REQUIRED_OUTPUT = {
    "status",
    "provider",
    "query_as_of",
    "data_as_of",
    "available_at",
    "feed",
    "is_delayed",
    "freshness",
    "quality_flags",
    "missingness",
    "records",
    "source",
    "citations",
    "warnings",
    "pagination",
    "trace_id",
}


async def tool_map(server: Any) -> dict[str, Any]:
    return {tool.name: tool for tool in await server.list_tools()}


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("name", "factory"),
    [
        ("sec", create_sec_server),
        ("market", create_market_server),
        ("analyst", create_analyst_server),
    ],
)
async def test_only_approved_tools_are_discoverable(name: str, factory: Any) -> None:
    tools = await tool_map(factory())
    assert set(tools) == EXPECTED_TOOLS[name]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("name", "factory"),
    [
        ("sec", create_sec_server),
        ("market", create_market_server),
        ("analyst", create_analyst_server),
    ],
)
async def test_tools_have_strict_inputs_structured_outputs_and_read_only_annotations(
    name: str, factory: Any
) -> None:
    tools = await tool_map(factory())
    snapshot = json.loads((CONTRACT_ROOT / f"{name}.json").read_text(encoding="utf-8"))

    for tool_name, tool in tools.items():
        assert tool.inputSchema["required"] == ["symbol", "as_of"]
        assert tool.inputSchema["additionalProperties"] is False
        assert set(tool.inputSchema["properties"]) == {"symbol", "as_of"}
        assert set(tool.outputSchema["required"]) == REQUIRED_OUTPUT
        assert tool.outputSchema["additionalProperties"] is False
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.idempotentHint is True
        assert tool.annotations.openWorldHint is True
        assert snapshot["tools"][tool_name] == {
            "inputSchema": tool.inputSchema,
            "outputSchema": tool.outputSchema,
            "annotations": tool.annotations.model_dump(by_alias=True, exclude_none=True),
        }
