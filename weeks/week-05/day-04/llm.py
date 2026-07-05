"""Вызов Dockhost Inference (OpenAI-compatible)."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import requests
from console_out import print_tagged
from dotenv import load_dotenv
from requests.exceptions import ConnectionError, HTTPError, Timeout

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

DEFAULT_MODEL = "deepseek/deepseek-v3.2"
DEFAULT_TIMEOUT = 45
MAX_RETRIES = 4
RETRY_BACKOFF_SEC = 2.0
RETRYABLE_HTTP = frozenset({429, 502, 503, 504})


def _api_key() -> str:
    key = os.environ.get("DOCKHOST_AI_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        print(
            "Задайте DOCKHOST_AI_KEY в .env (см. .env.example в корне репозитория).",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return key


def _base_url() -> str:
    return os.environ.get("OPENAI_BASE_URL", "https://inference.dockhost.io/v1").rstrip("/")


def _model() -> str:
    return os.environ.get("DOCKHOST_MODEL", DEFAULT_MODEL)


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


def complete(
    messages: list[dict[str, str]],
    *,
    timeout: int = DEFAULT_TIMEOUT,
    temperature: float | None = None,
) -> str:
    last_exc: BaseException | None = None
    payload: dict[str, object] = {"model": _model(), "messages": messages}
    if temperature is not None:
        payload["temperature"] = temperature
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(
                f"{_base_url()}/chat/completions",
                headers={
                    "Authorization": f"Bearer {_api_key()}",
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
            print_tagged(
                "retry",
                f"попытка {attempt}/{MAX_RETRIES} не удалась ({reason}), жду {wait:.0f}с…",
            )
            time.sleep(wait)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("LLM: исчерпаны попытки")
