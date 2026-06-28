"""MCP-сервер: scheduler tools (stdio)."""

from __future__ import annotations

import sys
from pathlib import Path

_MCP_DIR = Path(__file__).resolve().parent
if str(_MCP_DIR) not in sys.path:
    sys.path.insert(0, str(_MCP_DIR))

from mcp.server.fastmcp import FastMCP  # noqa: E402
from store import SchedulerStore  # noqa: E402

mcp = FastMCP(
    "scheduler",
    instructions="Schedule one-time and recurring agent reminders with SQLite persistence.",
)

_store = SchedulerStore()


@mcp.tool(
    description=(
        "Schedule a one-time reminder. After delay_seconds the host will dispatch "
        "prompt to the agent."
    )
)
def schedule_once(delay_seconds: int, prompt: str) -> dict:
    try:
        return _store.schedule_once(delay_seconds, prompt)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool(
    description=(
        "Schedule a recurring reminder using 5-field cron "
        "(minute hour day month weekday, UTC). Example: */5 * * * *"
    )
)
def schedule_recurring(cron: str, prompt: str) -> dict:
    try:
        return _store.schedule_recurring(cron, prompt)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool(
    description=(
        "Check due scheduled tasks, mark them as dispatched, and return aggregated stats. "
        "Called by the host ticker, not exposed to the LLM."
    )
)
def check_due() -> dict:
    return _store.check_due()


@mcp.tool(description="Delete all scheduled jobs from storage.")
def clear_jobs() -> dict:
    return _store.clear_all()


@mcp.tool(
    description=(
        "List pending and active scheduled jobs (once and recurring). "
        "Use before cancel_job to get job_id."
    )
)
def list_jobs() -> dict:
    return _store.list_jobs()


@mcp.tool(
    description=(
        "Cancel a pending one-time or active recurring job by job_id from list_jobs."
    )
)
def cancel_job(job_id: str) -> dict:
    try:
        return _store.cancel_job(job_id)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc


if __name__ == "__main__":
    mcp.run(transport="stdio")
