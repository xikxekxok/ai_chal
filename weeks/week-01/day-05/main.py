"""CLI: сравнение ответов LLM на слабой, средней и сильной модели."""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

REQUEST_TEMPERATURE = 0.7
ANALYSIS_TEMPERATURE = 0.0

DEFAULT_PROMPT = (
    "Опыт СССР — не эпитафия, а учебник. "
    "Какие уроки мировое пролетарское движение должно извлечь из этого опыта "
    "для периода после мировой пролетарской революции? "
    "С позиций марксизма, без либеральных штампов. "
    "3–4 урока: к каждому — два-три предложения. "
    "Фокус на будущем — что делать, а не пересказ прошлого."
)

ANALYSIS_MODEL = "qwen/qwen3.5-35b-a3b"

DOCKHOST_DOCS_URL = "https://docs.dockhost.ru/manual/ai/inference/use"
PRICES_URL = "https://dockhost.ru/prices"

ANALYSIS_SYSTEM_PROMPT = (
    "Ты аналитик качества ответов LLM. "
    "Сравни три ответа от слабой, средней и сильной модели на один запрос. "
    "Учти метрики: время, токены, стоимость. "
    "Кратко оцени качество, скорость и ресурсоёмкость каждой модели. "
    "Ответ на русском, лаконично: сравнение в 3–5 предложениях, "
    "затем по одному предложению — когда брать слабую, среднюю и сильную модель."
)


@dataclass(frozen=True)
class ModelTier:
    label: str
    model_id: str
    price_in_m: float
    price_out_m: float
    hf_url: str


MODELS: list[ModelTier] = [
    ModelTier(
        label="СЛАБАЯ",
        model_id="qwen/qwen3.5-9b",
        price_in_m=14.0,
        price_out_m=20.0,
        hf_url="https://huggingface.co/Qwen/Qwen3.5-9B",
    ),
    ModelTier(
        label="СРЕДНЯЯ",
        model_id="qwen/qwen3.5-35b-a3b",
        price_in_m=41.0,
        price_out_m=270.0,
        hf_url="https://huggingface.co/Qwen/Qwen3.5-35B-A3B",
    ),
    ModelTier(
        label="СИЛЬНАЯ",
        model_id="qwen/qwen3.7-max",
        price_in_m=169.0,
        price_out_m=506.0,
        hf_url="https://huggingface.co/Qwen/Qwen3-Max",
    ),
]


@dataclass
class ModelResult:
    tier: ModelTier
    content: str
    elapsed_sec: float
    prompt_tokens: int
    completion_tokens: int
    cost_rub: float


def get_config() -> tuple[str, str]:
    api_key = os.environ.get("DOCKHOST_AI_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print(
            "Задайте DOCKHOST_AI_KEY в .env (см. .env.example в корне репозитория).",
            file=sys.stderr,
        )
        sys.exit(1)

    base_url = os.environ.get("OPENAI_BASE_URL", "https://inference.dockhost.io/v1").rstrip("/")
    return api_key, base_url


def calc_cost(prompt_tokens: int, completion_tokens: int, tier: ModelTier) -> float:
    return (prompt_tokens * tier.price_in_m + completion_tokens * tier.price_out_m) / 1_000_000


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
    show_messages: bool = True,
) -> None:
    print(f"\n=== {label} ===")
    print(f"model: {model}")
    if show_messages:
        print("messages:")
        for msg in messages:
            print(f"  [{msg['role']}] {msg['content']}")
    else:
        print("messages: (не выводятся)")
    if extra_params:
        print(f"extra_params: {extra_params}")
    else:
        print("extra_params: (нет)")


def parse_usage(data: dict[str, Any]) -> tuple[str, int, int]:
    choice = data["choices"][0]
    content = choice["message"]["content"] or ""
    usage = data.get("usage") or {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)

    print(content)
    print(
        f"finish_reason: {choice.get('finish_reason', '?')} | "
        f"prompt_tokens: {prompt_tokens} | completion_tokens: {completion_tokens}"
    )
    return content, prompt_tokens, completion_tokens


def run_model(
    prompt: str,
    tier: ModelTier,
    *,
    api_key: str,
    base_url: str,
) -> ModelResult:
    messages = [{"role": "user", "content": prompt}]
    extra_params = {"temperature": REQUEST_TEMPERATURE}
    print_call_header(
        f"{tier.label}: {tier.model_id}",
        model=tier.model_id,
        messages=messages,
        extra_params=extra_params,
    )

    started = time.perf_counter()
    data = chat_completion(
        api_key=api_key,
        base_url=base_url,
        model=tier.model_id,
        messages=messages,
        extra_params=extra_params,
    )
    elapsed_sec = time.perf_counter() - started

    content, prompt_tokens, completion_tokens = parse_usage(data)
    cost_rub = calc_cost(prompt_tokens, completion_tokens, tier)
    print(
        f"elapsed: {elapsed_sec:.2f}s | cost: {cost_rub:.6f} ₽ "
        f"(вход {tier.price_in_m} ₽/1M, выход {tier.price_out_m} ₽/1M)"
    )
    return ModelResult(
        tier=tier,
        content=content,
        elapsed_sec=elapsed_sec,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_rub=cost_rub,
    )


def run_sweep(
    prompt: str,
    tiers: list[ModelTier],
    *,
    api_key: str,
    base_url: str,
) -> list[ModelResult]:
    return [run_model(prompt, tier, api_key=api_key, base_url=base_url) for tier in tiers]


def build_analysis_messages(prompt: str, results: list[ModelResult]) -> list[dict[str, str]]:
    answers = "\n\n".join(
        (
            f"--- {r.tier.label} ({r.tier.model_id}) ---\n"
            f"elapsed: {r.elapsed_sec:.2f}s | "
            f"prompt_tokens: {r.prompt_tokens} | "
            f"completion_tokens: {r.completion_tokens} | "
            f"cost: {r.cost_rub:.6f} ₽\n"
            f"{r.content}"
        )
        for r in results
    )
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
    results: list[ModelResult],
    *,
    api_key: str,
    base_url: str,
) -> None:
    messages = build_analysis_messages(prompt, results)
    extra_params = {"temperature": ANALYSIS_TEMPERATURE}
    print_call_header(
        f"АНАЛИЗ (temperature={ANALYSIS_TEMPERATURE})",
        model=ANALYSIS_MODEL,
        messages=messages,
        extra_params=extra_params,
        show_messages=False,
    )
    data = chat_completion(
        api_key=api_key,
        base_url=base_url,
        model=ANALYSIS_MODEL,
        messages=messages,
        extra_params=extra_params,
    )
    parse_usage(data)


def print_comparison(results: list[ModelResult]) -> None:
    print("\n=== СРАВНЕНИЕ ===")
    for result in results:
        print(
            f"{result.tier.label:8} | {result.tier.model_id} | "
            f"{result.elapsed_sec:.2f}s | "
            f"in={result.prompt_tokens} out={result.completion_tokens} | "
            f"{result.cost_rub:.6f} ₽"
        )
    print("→ На видео: заметны ли различия в глубине анализа, структуре и скорости?")


def print_links() -> None:
    print("\n=== ССЫЛКИ ===")
    print(f"- Dockhost Inference: {DOCKHOST_DOCS_URL}")
    print(f"- Тарифы: {PRICES_URL}")
    for tier in MODELS:
        print(f"- {tier.label} ({tier.model_id}): {tier.hf_url}")


def parse_args(argv: list[str]) -> tuple[argparse.Namespace, str]:
    parser = argparse.ArgumentParser(
        description="Сравнение ответов LLM на слабой, средней и сильной модели Dockhost.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--weak", action="store_true", help="Только слабая модель.")
    mode.add_argument("--medium", action="store_true", help="Только средняя модель.")
    mode.add_argument("--strong", action="store_true", help="Только сильная модель.")
    parser.add_argument(
        "--no-analysis",
        action="store_true",
        help="Только sweep по моделям, без анализа LLM.",
    )
    args, rest = parser.parse_known_args(argv)
    prompt = " ".join(rest).strip() or DEFAULT_PROMPT
    return args, prompt


def select_tiers(args: argparse.Namespace) -> list[ModelTier]:
    if args.weak:
        return [MODELS[0]]
    if args.medium:
        return [MODELS[1]]
    if args.strong:
        return [MODELS[2]]
    return MODELS


def main() -> None:
    args, prompt = parse_args(sys.argv[1:])
    api_key, base_url = get_config()
    tiers = select_tiers(args)

    print(f"base_url: {base_url}")
    print(f"prompt: {prompt}")
    print(f"models: {', '.join(t.model_id for t in tiers)}")

    results = run_sweep(prompt, tiers, api_key=api_key, base_url=base_url)
    print_comparison(results)

    if not args.no_analysis and len(results) == len(MODELS):
        run_analysis(prompt, results, api_key=api_key, base_url=base_url)

    if len(results) == len(MODELS):
        print_links()


if __name__ == "__main__":
    main()
