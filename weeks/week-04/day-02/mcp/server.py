"""MCP-сервер: web_search и read_page (stdio)."""

from __future__ import annotations

import sys
from pathlib import Path

_MCP_DIR = Path(__file__).resolve().parent
if str(_MCP_DIR) not in sys.path:
    sys.path.insert(0, str(_MCP_DIR))

from mcp.server.fastmcp import FastMCP  # noqa: E402
from page import fetch_page  # noqa: E402
from search import search_web  # noqa: E402

mcp = FastMCP(
    "web-search",
    instructions="Read-only web search and page reading for AI agents.",
)


@mcp.tool(description="Search the web. Returns titles, URLs, and snippets.")
def web_search(query: str, max_results: int = 5) -> dict:
    results = search_web(query, max_results=max_results)
    return {"query": query.strip(), "count": len(results), "results": results}


@mcp.tool(description="Fetch a web page and return title and main text content.")
def read_page(url: str) -> dict:
    return fetch_page(url)


if __name__ == "__main__":
    mcp.run(transport="stdio")
