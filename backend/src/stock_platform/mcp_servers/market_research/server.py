"""Price, news, and option aggregate MCP tools."""

from mcp.server.fastmcp import FastMCP

from stock_platform.application.market_data.repositories import PointInTimeRepository
from stock_platform.mcp_servers.common import McpAuditSink, create_read_only_server

TOOLS = {
    "get_price_bars": "price_bars",
    "get_company_news": "company_news",
    "get_option_aggregates": "option_aggregates",
}


def create_server(
    repository: PointInTimeRepository | None = None,
    audit_sink: McpAuditSink | None = None,
) -> FastMCP:
    return create_read_only_server("Market Research", TOOLS, repository, audit_sink)


mcp = create_server()
app = mcp.streamable_http_app()


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
