"""MCP-сервер: доска дедукции — улики и обвинение (stdio)."""

from __future__ import annotations

import sys
from pathlib import Path

_MCP_DIR = Path(__file__).resolve().parent
if str(_MCP_DIR) not in sys.path:
    sys.path.insert(0, str(_MCP_DIR))

from clues import get_store  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP(
    "snout",
    instructions="Deduction board: clues, theories, timeline, and accusation.",
)


@mcp.tool(
    description=(
        "Add a clue to the deduction board. Use tags like witness_marta, "
        "near_bushes, sasha_alibi, crow_too_heavy, weather_confirmed, time:18:38."
    )
)
def add_clue(fact: str, source: str, tags: list[str] | None = None) -> dict:
    try:
        return get_store().add_clue(fact, source, tags)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool(description="List all clues on the deduction board.")
def list_clues() -> dict:
    return get_store().list_clues()


@mcp.tool(
    description=(
        "Test a theory against collected clues. suspect_id: pete, crow, sasha, barbos. "
        "Returns verdict: supported, weak, or busted."
    )
)
def test_theory(suspect_id: str) -> dict:
    return get_store().test_theory(suspect_id)


@mcp.tool(description="Build timeline from clues tagged time:HH:MM.")
def build_timeline() -> dict:
    return get_store().build_timeline()


@mcp.tool(
    description=(
        "Accuse a suspect. Requires at least 3 clues and supported theory. "
        "suspect_id: pete, crow, sasha, barbos."
    )
)
def accuse(suspect_id: str) -> dict:
    result = get_store().accuse(suspect_id)
    if "error" in result:
        return result
    return result


@mcp.tool(description="Clear all clues from the deduction board.")
def clear_clues() -> dict:
    deleted = get_store().clear()
    return {"ok": True, "deleted": deleted}


if __name__ == "__main__":
    mcp.run(transport="stdio")
