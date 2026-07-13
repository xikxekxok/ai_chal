"""CLI: проверка Ollama, запуск сервера, stress-test."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests
import uvicorn

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from app.config import OPPOSSUM_JOKE_THEMES, load_config  # noqa: E402
from app.limits import ensure_system_prompt  # noqa: E402
from app.llm import (  # noqa: E402
    check_cloud_status,
    check_ollama_status,
    complete_chat,
)


def run_check() -> None:
    local = check_ollama_status()
    cloud = check_cloud_status()
    cfg = load_config()

    if local.get("ok"):
        print(
            f"[check] local: {local.get('ollama_url')} "
            f"model={local.get('model')} OK (think=on, stream)"
        )
    else:
        print(f"[check] local: FAIL — {local.get('error')}", file=sys.stderr)

    if cloud.get("ok"):
        print(f"[check] cloud: {cloud.get('base_url')} model={cloud.get('model')} OK")
    else:
        print(f"[check] cloud: unavailable — {cloud.get('error')}")

    if not local.get("ok") and not cloud.get("ok"):
        sys.exit(1)

    print("[check] app: opossum-jokes (local joke generator)")
    print(f"[check] themes: {len(OPPOSSUM_JOKE_THEMES)} hardcoded")
    print(f"[check] listen: {cfg.host}:{cfg.port}")
    print(
        f"[check] limits: rate={cfg.rate_limit_per_min}/min, "
        f"max_messages={cfg.max_messages}, max_chars={cfg.max_chars}, "
        f"num_ctx={cfg.num_ctx}, cloud_max_tokens={cfg.max_tokens}, "
        f"ollama_max_predict={cfg.ollama_max_predict or 'off'}, "
        f"ollama_temperature={cfg.ollama_temperature}"
    )
    print(f"[check] system_prompt: {len(cfg.system_prompt)} chars")


def run_serve() -> None:
    local = check_ollama_status()
    cloud = check_cloud_status()
    if not local.get("ok") and not cloud.get("ok"):
        print("[error] Нет доступного провайдера (local и cloud недоступны).", file=sys.stderr)
        if local.get("error"):
            print(f"[error] local: {local.get('error')}", file=sys.stderr)
        if cloud.get("error"):
            print(f"[error] cloud: {cloud.get('error')}", file=sys.stderr)
        sys.exit(1)
    cfg = load_config()
    print(f"[serve] http://{cfg.host}:{cfg.port}/")
    print(f"[serve] app: Анекдоты про опоссумов ({cfg.ollama_model})")
    uvicorn.run(
        "app.server:app",
        host=cfg.host,
        port=cfg.port,
        reload=False,
    )


def run_stress(count: int = 5) -> None:
    cfg = load_config()
    base = f"http://127.0.0.1:{cfg.port}"

    try:
        health = requests.get(f"{base}/api/health", timeout=5)
        health.raise_for_status()
    except requests.RequestException:
        print(
            f"[error] Сервер недоступен на {base}. Запустите: python {__file__} --serve",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"[stress] {count} sequential POST /api/chat on {base}")
    sample_themes = [t["label"] for t in OPPOSSUM_JOKE_THEMES[:3]]
    joke_prompt = (
        f"Напиши один короткий анекдот про опоссума, используя темы: "
        f"{', '.join(sample_themes)}."
    )
    prompts = [
        joke_prompt,
        "Reply with one word: hello.",
        "What is 2+2? Number only.",
        joke_prompt,
        "Say OK.",
    ]

    for i in range(count):
        prompt = prompts[i % len(prompts)]
        messages = ensure_system_prompt([], cfg.system_prompt)
        messages.append({"role": "user", "content": prompt})
        start = time.perf_counter()
        try:
            response = requests.post(
                f"{base}/api/chat",
                json={"messages": messages, "provider": "local"},
                timeout=300,
            )
            elapsed = int((time.perf_counter() - start) * 1000)
            if response.status_code == 429:
                print(f"[stress] {i + 1}/{count} rate limited (429) after {elapsed} ms")
                continue
            response.raise_for_status()
            data = response.json()
            preview = data.get("reply", "")[:80]
            print(
                f"[stress] {i + 1}/{count} OK latency={data.get('latency_ms')} ms "
                f"reply={preview!r}"
            )
        except requests.RequestException as exc:
            print(f"[stress] {i + 1}/{count} FAILED: {exc}", file=sys.stderr)
            sys.exit(1)

    print("[done] stress test finished")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Анекдоты про опоссумов — локальный генератор (FastAPI + Ollama)."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Проверить Ollama и модель без запуска сервера.",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Запустить веб-сервер (UI + API).",
    )
    parser.add_argument(
        "--stress",
        action="store_true",
        help="5 последовательных POST /api/chat (сервер должен быть запущен).",
    )
    parser.add_argument(
        "--stress-direct",
        action="store_true",
        help="Stress без HTTP-сервера: 3 прямых вызова Ollama (для демо стабильности).",
    )
    return parser.parse_args(argv)


def run_stress_direct(count: int = 3) -> None:
    status = check_ollama_status()
    if not status.get("ok"):
        print(f"[error] {status.get('error')}", file=sys.stderr)
        sys.exit(1)
    cfg = load_config()
    sample_themes = [t["label"] for t in OPPOSSUM_JOKE_THEMES[:2]]
    joke_prompt = (
        f"Напиши один короткий анекдот про опоссума, используя темы: "
        f"{', '.join(sample_themes)}."
    )
    print(f"[stress-direct] {count} calls to Ollama ({cfg.ollama_model})")
    for i in range(count):
        content = joke_prompt if i == 0 else f"Reply with digit {i + 1} only."
        messages = ensure_system_prompt(
            [{"role": "user", "content": content}],
            cfg.system_prompt,
        )
        result = complete_chat(messages, provider="local", config=cfg)
        print(
            f"[stress-direct] {i + 1}/{count} OK latency={result.latency_ms} ms "
            f"reply={result.content[:60]!r}"
        )
    print("[done] direct stress finished")


def main() -> None:
    args = parse_args(sys.argv[1:])
    if args.check:
        run_check()
    elif args.serve:
        run_serve()
    elif args.stress:
        run_stress()
    elif args.stress_direct:
        run_stress_direct()
    else:
        run_check()


if __name__ == "__main__":
    main()
