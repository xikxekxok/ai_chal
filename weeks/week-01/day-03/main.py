"""CLI: сравнение четырёх способов рассуждения LLM на одной задаче."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

DEFAULT_MODEL = "deepseek/deepseek-v3.2"

DEFAULT_TASK = (
    "Пять машин за пять минут проезжают пять миль. "
    "За сколько минут сто машин проедут сто миль? "
    "Объясни рассуждение и назови итоговое число минут."
)

EXPECTED_ANSWER = "5"

EXPERTS = [
    ("АНАЛИТИК", "Ты аналитик. Разбери условие, выдели ключевые допущения, дай решение."),
    ("ИНЖЕНЕР", "Ты инженер. Дай алгоритм рассуждения и финальный ответ."),
    ("КРИТИК", "Ты критик. Реши задачу и укажи типичные ошибки в рассуждении."),
]


@dataclass
class RunSummary:
    label: str
    completion_tokens: int
    calls: int = 1


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


def build_prompts(task: str) -> dict[str, str]:
    return {
        "direct": task,
        "step": f"{task}\n\nРешай пошагово.",
        "meta_generate": (
            f"Задача:\n{task}\n\n"
            "Составь один промпт, который поможет LLM решить эту задачу максимально точно. "
            "Верни только текст промпта, без пояснений и markdown."
        ),
    }


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


def print_call_header(
    label: str,
    *,
    model: str,
    messages: list[dict[str, str]],
    extra_params: dict[str, Any] | None = None,
) -> None:
    print(f"\n=== {label} ===")
    print(f"model: {model}")
    print("messages:")
    for msg in messages:
        print(f"  [{msg['role']}] {msg['content']}")
    if extra_params:
        print(f"extra_params: {extra_params}")
    else:
        print("extra_params: (нет)")


def print_response(data: dict[str, Any]) -> int:
    choice = data["choices"][0]
    content = choice["message"]["content"] or ""
    usage = data.get("usage") or {}
    tokens = int(usage.get("completion_tokens") or 0)

    print(content)
    print(f"finish_reason: {choice.get('finish_reason', '?')} | completion_tokens: {tokens}")
    return tokens


def run_direct(
    task: str,
    *,
    api_key: str,
    base_url: str,
    model: str,
) -> RunSummary:
    prompts = build_prompts(task)
    messages = [{"role": "user", "content": prompts["direct"]}]
    print_call_header("СПОСОБ 1: Прямой ответ", model=model, messages=messages)
    data = chat_completion(api_key=api_key, base_url=base_url, model=model, messages=messages)
    tokens = print_response(data)
    return RunSummary("direct", tokens)


def run_step(
    task: str,
    *,
    api_key: str,
    base_url: str,
    model: str,
) -> RunSummary:
    prompts = build_prompts(task)
    messages = [{"role": "user", "content": prompts["step"]}]
    print_call_header("СПОСОБ 2: Пошагово", model=model, messages=messages)
    data = chat_completion(api_key=api_key, base_url=base_url, model=model, messages=messages)
    tokens = print_response(data)
    return RunSummary("step", tokens)


def run_meta(
    task: str,
    *,
    api_key: str,
    base_url: str,
    model: str,
) -> RunSummary:
    prompts = build_prompts(task)
    generate_messages = [{"role": "user", "content": prompts["meta_generate"]}]
    print_call_header(
        "СПОСОБ 3 — ШАГ 1: Генерация промпта",
        model=model,
        messages=generate_messages,
    )
    generate_data = chat_completion(
        api_key=api_key,
        base_url=base_url,
        model=model,
        messages=generate_messages,
    )
    generate_tokens = print_response(generate_data)
    generated_prompt = (generate_data["choices"][0]["message"]["content"] or "").strip()

    solve_messages = [{"role": "user", "content": generated_prompt}]
    print_call_header(
        "СПОСОБ 3 — ШАГ 2: Решение по сгенерированному промпту",
        model=model,
        messages=solve_messages,
    )
    solve_data = chat_completion(
        api_key=api_key,
        base_url=base_url,
        model=model,
        messages=solve_messages,
    )
    solve_tokens = print_response(solve_data)
    return RunSummary("meta", generate_tokens + solve_tokens, calls=2)


def run_experts(
    task: str,
    *,
    api_key: str,
    base_url: str,
    model: str,
) -> list[RunSummary]:
    summaries: list[RunSummary] = []
    for expert_label, system_prompt in EXPERTS:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]
        print_call_header(
            f"СПОСОБ 4: Эксперт — {expert_label}",
            model=model,
            messages=messages,
        )
        data = chat_completion(
            api_key=api_key,
            base_url=base_url,
            model=model,
            messages=messages,
        )
        tokens = print_response(data)
        summaries.append(RunSummary(expert_label.lower(), tokens))
    return summaries


def print_comparison(
    summaries: list[RunSummary],
    *,
    task: str,
    expert_summaries: list[RunSummary] | None = None,
) -> None:
    print("\n=== СРАВНЕНИЕ ===")
    print(f"Эталонный ответ: {EXPECTED_ANSWER} минут")
    print(f"Задача: {task}")

    for summary in summaries:
        calls_note = f", вызовов: {summary.calls}" if summary.calls > 1 else ""
        print(f"{summary.label}: completion_tokens={summary.completion_tokens}{calls_note}")

    if expert_summaries:
        parts = ", ".join(f"{s.label}={s.completion_tokens}" for s in expert_summaries)
        total = sum(s.completion_tokens for s in expert_summaries)
        print(f"experts (сумма): {parts} | итого tokens={total}, вызовов: 3")

    print(f"→ На видео: отличаются ли ответы? Какой способ ближе к {EXPECTED_ANSWER} минутам?")


def parse_args(argv: list[str]) -> tuple[argparse.Namespace, str]:
    parser = argparse.ArgumentParser(
        description="Сравнение четырёх способов рассуждения LLM на одной задаче.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--direct", action="store_true", help="Только прямой ответ.")
    mode.add_argument("--step", action="store_true", help="Только пошаговое решение.")
    mode.add_argument(
        "--meta",
        action="store_true",
        help="Только meta-prompt: генерация промпта и решение.",
    )
    mode.add_argument(
        "--experts",
        action="store_true",
        help="Только панель экспертов (аналитик, инженер, критик).",
    )
    args, rest = parser.parse_known_args(argv)
    task = " ".join(rest).strip() or DEFAULT_TASK
    return args, task


def main() -> None:
    args, task = parse_args(sys.argv[1:])
    api_key, base_url, model = get_config()

    print(f"model: {model}")
    print(f"base_url: {base_url}")
    print(f"task: {task}")

    if args.direct:
        summary = run_direct(task, api_key=api_key, base_url=base_url, model=model)
        print_comparison([summary], task=task)
        return

    if args.step:
        summary = run_step(task, api_key=api_key, base_url=base_url, model=model)
        print_comparison([summary], task=task)
        return

    if args.meta:
        summary = run_meta(task, api_key=api_key, base_url=base_url, model=model)
        print_comparison([summary], task=task)
        return

    if args.experts:
        expert_summaries = run_experts(task, api_key=api_key, base_url=base_url, model=model)
        print_comparison([], task=task, expert_summaries=expert_summaries)
        return

    summaries = [
        run_direct(task, api_key=api_key, base_url=base_url, model=model),
        run_step(task, api_key=api_key, base_url=base_url, model=model),
        run_meta(task, api_key=api_key, base_url=base_url, model=model),
    ]
    expert_summaries = run_experts(task, api_key=api_key, base_url=base_url, model=model)
    print_comparison(summaries, task=task, expert_summaries=expert_summaries)


if __name__ == "__main__":
    main()
