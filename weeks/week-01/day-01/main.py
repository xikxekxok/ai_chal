"""Минимальный CLI: запрос к LLM через Dockhost (OpenAI-compatible API)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# .env в корне репозитория
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

DEFAULT_MODEL = "deepseek/deepseek-v3.2"
DEFAULT_PROMPT = "Привет! Ответь одним коротким предложением: что ты умеешь?"


def main() -> None:
    api_key = os.environ.get("DOCKHOST_AI_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print(
            "Задайте DOCKHOST_AI_KEY в .env (см. .env.example в корне репозитория).",
            file=sys.stderr,
        )
        sys.exit(1)

    base_url = os.environ.get("OPENAI_BASE_URL", "https://inference.dockhost.io/v1")
    model = os.environ.get("DOCKHOST_MODEL", DEFAULT_MODEL)
    prompt = " ".join(sys.argv[1:]).strip() or DEFAULT_PROMPT

    client = OpenAI(base_url=base_url, api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    print(response.choices[0].message.content or "")


if __name__ == "__main__":
    main()
