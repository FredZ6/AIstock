"""Export or verify the public MCP tool contract snapshots."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from stock_platform.mcp_servers.analyst_research.server import (
    create_server as create_analyst_server,
)
from stock_platform.mcp_servers.market_research.server import create_server as create_market_server
from stock_platform.mcp_servers.sec_research.server import create_server as create_sec_server

ROOT = Path(__file__).resolve().parents[1] / "contracts" / "mcp"
FACTORIES: dict[str, Callable[[], FastMCP]] = {
    "sec": create_sec_server,
    "market": create_market_server,
    "analyst": create_analyst_server,
}


async def snapshot(factory: Callable[[], FastMCP]) -> dict[str, Any]:
    tools = await factory().list_tools()
    return {
        "tools": {
            tool.name: {
                "inputSchema": tool.inputSchema,
                "outputSchema": tool.outputSchema,
                "annotations": tool.annotations.model_dump(by_alias=True, exclude_none=True),
            }
            for tool in sorted(tools, key=lambda item: item.name)
        }
    }


async def main(check: bool) -> int:
    for name, factory in FACTORIES.items():
        content = json.dumps(await snapshot(factory), indent=2, sort_keys=True) + "\n"
        path = ROOT / f"{name}.json"
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                print(f"MCP contract drift: {path}")
                return 1
        else:
            path.write_text(content, encoding="utf-8")
            print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    raise SystemExit(asyncio.run(main(parser.parse_args().check)))
