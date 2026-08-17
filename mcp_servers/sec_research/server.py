"""SEC facts, filings, and filing-section MCP tools."""

from mcp.server.fastmcp import FastMCP
from stock_platform.application.market_data.repositories import PointInTimeRepository

from mcp_servers.common import create_read_only_server

TOOLS = {
    "get_company_facts": "company_facts",
    "get_filings": "filings",
    "get_filing_sections": "filing_sections",
}


def create_server(repository: PointInTimeRepository | None = None) -> FastMCP:
    return create_read_only_server("SEC Research", TOOLS, repository)


mcp = create_server()
app = mcp.streamable_http_app()


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
