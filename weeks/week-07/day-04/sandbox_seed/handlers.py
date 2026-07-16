"""UI-ish helpers for the sandbox project."""

from __future__ import annotations

from api import fetch_user


def build_user_card(user: dict[str, str | int]) -> str:
    return f"{user['id']}: {user['name']} ({user['status']})"


def load_featured_user() -> str:
    featured = fetch_user(42)
    return build_user_card(featured)
