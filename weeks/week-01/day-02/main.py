"""CLI: сравнение ответа LLM без ограничений и с параметрами API."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

DEFAULT_MODEL = "deepseek/deepseek-v3.2"
DEFAULT_PROMPT = (
    "Перечисли пять полезных советов начинающему Python-разработчику. "
    "Для каждого совета дай развёрнутое объяснение с примером."
)
JSON_SYSTEM_PROMPT = 'Ответ — валидный JSON: {"items": [{"title": str, "text": str}]}'
CONTROLLED_MAX_TOKENS = 80
CONTROLLED_STOP = ["---"]


def get_config() -> tuple[str, str, str]:
    api_key = os.environ.get("DOCKHOST_AI_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print(
            "Задайте DOCKHOST_AI_KEY в .env (см. .env.example в корне репозитория).",
            file=sys.stderr,
        )
        sys.exit(1)

    base_url = os.environ.get("OPENAI_BASE_URL", "https://inference.dockhost.io/v1").rstrip("/")
    model = os.environ.get("DOCKHOST_MODEL", DEFAULT_MODEL)
    return api_key, base_url, model


def chat_completion(
    *,
    api_key: str,
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    extra_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"model": model, "messages": messages}
    if extra_params:
        body.update(extra_params)

    response = requests.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def run_baseline(
    prompt: str,
    *,
    api_key: str,
    base_url: str,
    model: str,
) -> dict[str, Any]:
    return chat_completion(
        api_key=api_key,
        base_url=base_url,
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )


def run_controlled(
    prompt: str,
    *,
    api_key: str,
    base_url: str,
    model: str,
) -> dict[str, Any]:
    return chat_completion(
        api_key=api_key,
        base_url=base_url,
        model=model,
        messages=[
            {"role": "system", "content": JSON_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        extra_params={
            "response_format": {"type": "json_object"},
            "max_tokens": CONTROLLED_MAX_TOKENS,
            "stop": CONTROLLED_STOP,
        },
    )


def print_result(label: str, data: dict[str, Any], *, api_note: str = "") -> None:
    choice = data["choices"][0]
    content = choice["message"]["content"] or ""
    usage = data.get("usage") or {}

    print(f"\n=== {label} ===")
    if api_note:
        print(api_note)
    print(content)
    print(
        f"finish_reason: {choice.get('finish_reason', '?')} | "
        f"completion_tokens: {usage.get('completion_tokens', '?')}"
    )


def parse_args(argv: list[str]) -> tuple[argparse.Namespace, str]:
    parser = argparse.ArgumentParser(
        description="Сравнение ответа LLM: без ограничений vs параметры API.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--baseline",
        action="store_true",
        help="Только запрос без ограничений.",
    )
    mode.add_argument(
        "--controlled",
        action="store_true",
        help="Только запрос с response_format, max_tokens и stop.",
    )
    args, rest = parser.parse_known_args(argv)
    prompt = " ".join(rest).strip() or DEFAULT_PROMPT
    return args, prompt


def main() -> None:
    args, prompt = parse_args(sys.argv[1:])
    api_key, base_url, model = get_config()

    if args.baseline:
        data = run_baseline(prompt, api_key=api_key, base_url=base_url, model=model)
        print_result("БЕЗ ОГРАНИЧЕНИЙ", data)
        return

    if args.controlled:
        data = run_controlled(prompt, api_key=api_key, base_url=base_url, model=model)
        print_result(
            "С ОГРАНИЧЕНИЯМИ",
            data,
            api_note=(
                f"API: response_format=json_object, "
                f"max_tokens={CONTROLLED_MAX_TOKENS}, stop={CONTROLLED_STOP!r}"
            ),
        )
        return

    baseline_data = run_baseline(prompt, api_key=api_key, base_url=base_url, model=model)
    print_result("БЕЗ ОГРАНИЧЕНИЙ", baseline_data)

    controlled_data = run_controlled(prompt, api_key=api_key, base_url=base_url, model=model)
    print_result(
        "С ОГРАНИЧЕНИЯМИ",
        controlled_data,
        api_note=(
            f"API: response_format=json_object, "
            f"max_tokens={CONTROLLED_MAX_TOKENS}, stop={CONTROLLED_STOP!r}"
        ),
    )


if __name__ == "__main__":
    main()
