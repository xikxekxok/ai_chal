"""MCP-сервер: архив дела missing_ball (stdio)."""

from __future__ import annotations

import sys
from pathlib import Path

_MCP_DIR = Path(__file__).resolve().parent
if str(_MCP_DIR) not in sys.path:
    sys.path.insert(0, str(_MCP_DIR))

from case import list_case_files as _list_case_files  # noqa: E402
from case import list_suspects as _list_suspects  # noqa: E402
from case import read_case_file as _read_case_file  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP(
    "burrow",
    instructions="Case archive for the missing ball of Tofik the opossum.",
)


@mcp.tool(description="List available case documents in the burrow archive.")
def list_case_files() -> dict:
    return _list_case_files()


@mcp.tool(
    description=(
        "Read a case document by exact file_id. "
        "Allowed: yard_report, witness_marta, gazebo_log, shed_findings, suspects. "
        "Call list_case_files first if unsure."
    )
)
def read_case_file(file_id: str) -> dict:
    try:
        return _read_case_file(file_id)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool(description="List suspects with motives and alibis for missing_ball.")
def list_suspects() -> dict:
    return _list_suspects()


if __name__ == "__main__":
    mcp.run(transport="stdio")
