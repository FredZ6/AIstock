"""Analyst estimate and target consensus MCP tools."""

from mcp.server.fastmcp import FastMCP

from stock_platform.application.market_data.repositories import PointInTimeRepository
from stock_platform.mcp_servers.common import McpAuditSink, create_read_only_server

TOOLS = {
    "get_estimates": "estimates",
    "get_target_consensus": "target_consensus",
}


def create_server(
    repository: PointInTimeRepository | None = None,
    audit_sink: McpAuditSink | None = None,
) -> FastMCP:
    return create_read_only_server("Analyst Research", TOOLS, repository, audit_sink)


mcp = create_server()
app = mcp.streamable_http_app()


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
