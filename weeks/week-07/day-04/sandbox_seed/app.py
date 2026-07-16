"""Main app entry for the sandbox project."""

from __future__ import annotations

from api import fetch_user
from handlers import build_user_card


def run() -> None:
    user = fetch_user(7)
    print(build_user_card(user))


if __name__ == "__main__":
    run()
