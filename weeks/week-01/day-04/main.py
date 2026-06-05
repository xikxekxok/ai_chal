"""CLI: сравнение ответов LLM при разных значениях temperature."""

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

DEFAULT_PROMPT = (
    "Ты агитатор на митинге в духе марксизма-ленинизма. "
    "Придумай три разных лозунга о пролетарской революции против буржуазии. "
    "К каждому — одно предложение пояснения. "
    "Допустим здоровый юмор, но без оскорблений и призывов к насилию."
)

TEMPERATURES = [0.0, 0.7, 1.2]
ANALYSIS_TEMPERATURE = 0.0

ANALYSIS_SYSTEM_PROMPT = (
    "Ты аналитик качества ответов LLM. "
    "Сравни три ответа на один и тот же запрос с разной temperature. "
    "Оцени каждый ответ по критериям: точность (связность, формат, уместность), "
    "креативность (оригинальность, образность, юмор), "
    "разнообразие (насколько ответы отличаются друг от друга). "
    "Затем сформулируй, для каких типов задач лучше подходит каждая настройка "
    "temperature: 0, 0.7 и 1.2. "
    "Ответ структурируй на русском: краткое сравнение трёх ответов, "
    "затем рекомендации по задачам для каждой temperature."
)


@dataclass
class TempResult:
    temperature: float
    content: str
    completion_tokens: int


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


def print_response(data: dict[str, Any]) -> tuple[str, int]:
    choice = data["choices"][0]
    content = choice["message"]["content"] or ""
    usage = data.get("usage") or {}
    tokens = int(usage.get("completion_tokens") or 0)

    print(content)
    print(f"finish_reason: {choice.get('finish_reason', '?')} | completion_tokens: {tokens}")
    return content, tokens


def run_temperature(
    prompt: str,
    temperature: float,
    *,
    api_key: str,
    base_url: str,
    model: str,
) -> TempResult:
    messages = [{"role": "user", "content": prompt}]
    extra_params = {"temperature": temperature}
    print_call_header(
        f"TEMPERATURE = {temperature}",
        model=model,
        messages=messages,
        extra_params=extra_params,
    )
    data = chat_completion(
        api_key=api_key,
        base_url=base_url,
        model=model,
        messages=messages,
        extra_params=extra_params,
    )
    content, tokens = print_response(data)
    return TempResult(temperature=temperature, content=content, completion_tokens=tokens)


def run_sweep(
    prompt: str,
    temperatures: list[float],
    *,
    api_key: str,
    base_url: str,
    model: str,
) -> list[TempResult]:
    return [
        run_temperature(
            prompt,
            temp,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        for temp in temperatures
    ]


def build_analysis_messages(prompt: str, results: list[TempResult]) -> list[dict[str, str]]:
    answers = "\n\n".join(f"--- temperature = {r.temperature} ---\n{r.content}" for r in results)
    user_content = (
        f"Исходный запрос пользователя:\n{prompt}\n\n"
        f"Ответы LLM:\n{answers}\n\n"
        "Проанализируй ответы и сформулируй выводы."
    )
    return [
        {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def run_analysis(
    prompt: str,
    results: list[TempResult],
    *,
    api_key: str,
    base_url: str,
    model: str,
) -> int:
    messages = build_analysis_messages(prompt, results)
    extra_params = {"temperature": ANALYSIS_TEMPERATURE}
    print_call_header(
        f"АНАЛИЗ (temperature={ANALYSIS_TEMPERATURE})",
        model=model,
        messages=messages,
        extra_params=extra_params,
    )
    data = chat_completion(
        api_key=api_key,
        base_url=base_url,
        model=model,
        messages=messages,
        extra_params=extra_params,
    )
    _, tokens = print_response(data)
    return tokens


def print_comparison(results: list[TempResult], *, prompt: str) -> None:
    print("\n=== СРАВНЕНИЕ ===")
    print(f"Промпт: {prompt}")
    for result in results:
        print(f"temperature={result.temperature}: completion_tokens={result.completion_tokens}")
    print("→ На видео: заметны ли различия в юморе, формулировках, предсказуемости?")


def parse_args(argv: list[str]) -> tuple[argparse.Namespace, str]:
    parser = argparse.ArgumentParser(
        description="Сравнение ответов LLM при temperature 0, 0.7 и 1.2.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--temp0", action="store_true", help="Только temperature=0.")
    mode.add_argument("--temp07", action="store_true", help="Только temperature=0.7.")
    mode.add_argument("--temp12", action="store_true", help="Только temperature=1.2.")
    parser.add_argument(
        "--no-analysis",
        action="store_true",
        help="Только sweep по температурам, без анализа LLM.",
    )
    args, rest = parser.parse_known_args(argv)
    prompt = " ".join(rest).strip() or DEFAULT_PROMPT
    return args, prompt


def main() -> None:
    args, prompt = parse_args(sys.argv[1:])
    api_key, base_url, model = get_config()

    print(f"model: {model}")
    print(f"base_url: {base_url}")
    print(f"prompt: {prompt}")

    if args.temp0:
        results = run_sweep(
            prompt,
            [0.0],
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        print_comparison(results, prompt=prompt)
        return

    if args.temp07:
        results = run_sweep(
            prompt,
            [0.7],
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        print_comparison(results, prompt=prompt)
        return

    if args.temp12:
        results = run_sweep(
            prompt,
            [1.2],
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        print_comparison(results, prompt=prompt)
        return

    results = run_sweep(
        prompt,
        TEMPERATURES,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
    print_comparison(results, prompt=prompt)

    if not args.no_analysis:
        run_analysis(
            prompt,
            results,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )


if __name__ == "__main__":
    main()
