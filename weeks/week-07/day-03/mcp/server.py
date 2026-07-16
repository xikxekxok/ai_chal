from __future__ import annotations

import json
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

DAY_DIR = Path(__file__).resolve().parents[1]
CRM_PATH = DAY_DIR / "data" / "crm.json"

mcp = FastMCP(
    "notesync-crm",
    instructions="Read-only CRM for tickets and users.",
)


def _load_crm() -> dict[str, object]:
    return json.loads(CRM_PATH.read_text(encoding="utf-8"))


def _find_by_id(items: list[dict[str, object]], item_id: str) -> dict[str, object]:
    for item in items:
        if item.get("id") == item_id:
            return item
    raise ValueError(f"not found: {item_id}")


@mcp.tool(description="List support tickets from local CRM JSON.")
def list_tickets(status: str | None = None, user_id: str | None = None) -> dict[str, object]:
    crm = _load_crm()
    tickets = list(crm["tickets"])
    if status:
        tickets = [ticket for ticket in tickets if ticket.get("status") == status]
    if user_id:
        tickets = [ticket for ticket in tickets if ticket.get("user_id") == user_id]
    return {"count": len(tickets), "tickets": tickets}


@mcp.tool(description="Get one support ticket by ticket id, for example T-1042.")
def get_ticket(ticket_id: str) -> dict[str, object]:
    crm = _load_crm()
    ticket = _find_by_id(list(crm["tickets"]), ticket_id)
    return {"ticket": ticket}


@mcp.tool(description="Get one CRM user by user id, for example U-100.")
def get_user(user_id: str) -> dict[str, object]:
    crm = _load_crm()
    user = _find_by_id(list(crm["users"]), user_id)
    return {"user": user}


if __name__ == "__main__":
    if str(DAY_DIR) not in sys.path:
        sys.path.insert(0, str(DAY_DIR))
    mcp.run(transport="stdio")
