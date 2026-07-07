"""Вызов локальной LLM через Ollama (OpenAI-compatible API)."""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen3:8b"
DEFAULT_THINK = False
REQUEST_TIMEOUT = 180


@dataclass
class OllamaConfig:
    base_url: str
    model: str
    think: bool


@dataclass
class CompletionResult:
    content: str
    usage: dict[str, Any]
    latency_ms: int


def load_ollama_config() -> OllamaConfig:
    think_raw = os.environ.get("OLLAMA_THINK", str(DEFAULT_THINK)).lower()
    return OllamaConfig(
        base_url=os.environ.get("OLLAMA_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        model=os.environ.get("OLLAMA_CHAT_MODEL", DEFAULT_MODEL),
        think=think_raw in {"1", "true", "yes"},
    )


def check_ollama(config: OllamaConfig | None = None) -> None:
    cfg = config or load_ollama_config()
    try:
        response = requests.get(f"{cfg.base_url}/api/tags", timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(
            f"[error] Ollama недоступен на {cfg.base_url}. Запустите: ollama serve",
            file=sys.stderr,
        )
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)

    tags = response.json().get("models", [])
    model_names = {item.get("name", "") for item in tags}
    if cfg.model not in model_names and f"{cfg.model}:latest" not in model_names:
        print(
            f"[error] Модель {cfg.model} не найдена. Выполните: ollama pull {cfg.model}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"[check] server: {cfg.base_url} OK")
    print(f"[check] model: {cfg.model} OK")


def complete_local(
    messages: list[dict[str, str]],
    config: OllamaConfig | None = None,
) -> CompletionResult:
    cfg = config or load_ollama_config()
    start = time.perf_counter()
    try:
        response = requests.post(
            f"{cfg.base_url}/v1/chat/completions",
            json={
                "model": cfg.model,
                "messages": messages,
                "stream": False,
                "think": cfg.think,
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"[error] запрос к Ollama не удался: {exc}", file=sys.stderr)
        sys.exit(1)

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    data = response.json()
    content = data["choices"][0]["message"].get("content") or ""
    if not content:
        print("[error] LLM вернул пустой ответ.", file=sys.stderr)
        sys.exit(1)

    return CompletionResult(
        content=content,
        usage=data.get("usage") or {},
        latency_ms=elapsed_ms,
    )
