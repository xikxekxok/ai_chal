"""MCP-сервер: web_search, read_page, build_report, save_note (stdio)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_MCP_DIR = Path(__file__).resolve().parent
if str(_MCP_DIR) not in sys.path:
    sys.path.insert(0, str(_MCP_DIR))

from mcp.server.fastmcp import FastMCP  # noqa: E402
from notes import build_report as _build_report  # noqa: E402
from notes import save_note as _save_note  # noqa: E402
from page import fetch_page  # noqa: E402
from search import search_web  # noqa: E402

mcp = FastMCP(
    "notes-pipeline",
    instructions=(
        "Web search, page reading, report building, and note saving for AI agents."
    ),
)


@mcp.tool(description="Search the web. Returns titles, URLs, and snippets.")
def web_search(query: str, max_results: int = 5) -> dict:
    results = search_web(query, max_results=max_results)
    return {"query": query.strip(), "count": len(results), "results": results}


@mcp.tool(description="Fetch a web page and return title and main text content.")
def read_page(url: str) -> dict:
    return fetch_page(url)


@mcp.tool(
    description=(
        "Build a structured markdown report from search findings. "
        "Call after web_search (and optionally read_page). "
        "Pass bullet findings and optional sources from search results."
    )
)
def build_report(
    topic: str,
    findings: str,
    sources: list[dict[str, Any]] | None = None,
) -> dict:
    return _build_report(topic, findings, sources)


@mcp.tool(
    description=(
        "Save markdown note to data/notes/. Call after build_report with its markdown field. "
        "filename is basename only, e.g. mcp_facts.md"
    )
)
def save_note(filename: str, content: str) -> dict:
    return _save_note(filename, content)


if __name__ == "__main__":
    mcp.run(transport="stdio")
