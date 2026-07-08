"""Локальная (Ollama) и облачная (Dockhost) генерация."""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from requests.exceptions import ConnectionError, HTTPError, Timeout

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen3:8b"
DEFAULT_OLLAMA_THINK = False
LOCAL_TIMEOUT = 300

DEFAULT_CLOUD_MODEL = "deepseek/deepseek-v3.2"
CLOUD_TIMEOUT = 45
MAX_RETRIES = 4
RETRY_BACKOFF_SEC = 2.0
RETRYABLE_HTTP = frozenset({429, 502, 503, 504})


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
    think_raw = os.environ.get("OLLAMA_THINK", str(DEFAULT_OLLAMA_THINK)).lower()
    return OllamaConfig(
        base_url=os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL).rstrip("/"),
        model=os.environ.get("OLLAMA_CHAT_MODEL", DEFAULT_OLLAMA_MODEL),
        think=think_raw in {"1", "true", "yes"},
    )


def _cloud_api_key() -> str:
    key = os.environ.get("DOCKHOST_AI_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        print(
            "Задайте DOCKHOST_AI_KEY в .env (см. .env.example в корне репозитория).",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return key


def _cloud_base_url() -> str:
    return os.environ.get("OPENAI_BASE_URL", "https://inference.dockhost.io/v1").rstrip("/")


def _cloud_model() -> str:
    return os.environ.get("DOCKHOST_MODEL", DEFAULT_CLOUD_MODEL)


def _retry_reason(exc: BaseException) -> str:
    if isinstance(exc, Timeout):
        return "таймаут"
    if isinstance(exc, ConnectionError):
        return "сеть"
    if isinstance(exc, HTTPError) and exc.response is not None:
        return f"HTTP {exc.response.status_code}"
    return type(exc).__name__


def _should_retry(exc: BaseException, attempt: int, max_retries: int) -> bool:
    if attempt >= max_retries:
        return False
    if isinstance(exc, (Timeout, ConnectionError)):
        return True
    if isinstance(exc, HTTPError) and exc.response is not None:
        return exc.response.status_code in RETRYABLE_HTTP
    return False


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

    embed_model = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    if embed_model not in model_names and f"{embed_model}:latest" not in model_names:
        print(
            f"[error] Модель {embed_model} не найдена. Выполните: ollama pull {embed_model}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"[check] server: {cfg.base_url} OK")
    print(f"[check] model: {cfg.model} OK")
    print(f"[check] embed: {embed_model} OK")


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
            timeout=LOCAL_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"[error] запрос к Ollama не удался: {exc}", file=sys.stderr)
        sys.exit(1)

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    data = response.json()
    content = data["choices"][0]["message"].get("content") or ""
    if not content:
        print("[error] локальная LLM вернула пустой ответ.", file=sys.stderr)
        sys.exit(1)

    return CompletionResult(
        content=content,
        usage=data.get("usage") or {},
        latency_ms=elapsed_ms,
    )


def complete_cloud(
    messages: list[dict[str, str]],
    *,
    timeout: int = CLOUD_TIMEOUT,
    temperature: float | None = None,
) -> str:
    last_exc: BaseException | None = None
    payload: dict[str, object] = {"model": _cloud_model(), "messages": messages}
    if temperature is not None:
        payload["temperature"] = temperature
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(
                f"{_cloud_base_url()}/chat/completions",
                headers={
                    "Authorization": f"Bearer {_cloud_api_key()}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )
            if response.status_code in RETRYABLE_HTTP:
                response.raise_for_status()
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"].get("content") or ""
        except (Timeout, ConnectionError, HTTPError) as exc:
            last_exc = exc
            if not _should_retry(exc, attempt, MAX_RETRIES):
                raise
            wait = RETRY_BACKOFF_SEC * attempt
            reason = _retry_reason(exc)
            print(
                f"[retry] cloud попытка {attempt}/{MAX_RETRIES} не удалась ({reason}), "
                f"жду {wait:.0f}с…",
                file=sys.stderr,
            )
            time.sleep(wait)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("cloud LLM: исчерпаны попытки")
