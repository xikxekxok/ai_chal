"""Tiny API layer for the sandbox project."""

from __future__ import annotations


def fetch_user(user_id: int) -> dict[str, str | int]:
    return {
        "id": user_id,
        "name": f"user-{user_id}",
        "status": "active",
    }
