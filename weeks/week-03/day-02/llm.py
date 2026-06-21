"""Вызов Dockhost Inference (OpenAI-compatible)."""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from requests.exceptions import ConnectionError, HTTPError, Timeout

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

DEFAULT_MODEL = "deepseek/deepseek-v3.2"
DEFAULT_TIMEOUT = 45
MAX_RETRIES = 4
RETRY_BACKOFF_SEC = 2.0
RETRYABLE_HTTP = frozenset({429, 502, 503, 504})

PRICE_IN_M = 35.0
PRICE_OUT_M = 51.0


@dataclass
class LlmConfig:
    api_key: str
    base_url: str
    model: str = DEFAULT_MODEL


@dataclass
class UsageTracker:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_rub: float = 0.0
    calls: int = 0

    def record(self, usage: dict[str, Any]) -> dict[str, int]:
        prompt = int(usage.get("prompt_tokens") or 0)
        completion = int(usage.get("completion_tokens") or 0)
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.cost_rub += (prompt * PRICE_IN_M + completion * PRICE_OUT_M) / 1_000_000
        self.calls += 1
        return {"prompt_tokens": prompt, "completion_tokens": completion}


def load_llm_config() -> LlmConfig:
    api_key = os.environ.get("DOCKHOST_AI_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print(
            "Задайте DOCKHOST_AI_KEY в .env (см. .env.example в корне репозитория).",
            file=sys.stderr,
        )
        sys.exit(1)
    base_url = os.environ.get("OPENAI_BASE_URL", "https://inference.dockhost.io/v1").rstrip("/")
    model = os.environ.get("DOCKHOST_MODEL", DEFAULT_MODEL)
    return LlmConfig(api_key=api_key, base_url=base_url, model=model)


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
    config: LlmConfig,
    messages: list[dict[str, str]],
    *,
    tracker: UsageTracker | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    max_retries: int = MAX_RETRIES,
) -> tuple[str, dict[str, Any]]:
    last_exc: BaseException | None = None
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(
                f"{config.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": config.model, "messages": messages},
                timeout=timeout,
            )
            if response.status_code in RETRYABLE_HTTP:
                response.raise_for_status()
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"].get("content") or ""
            usage = data.get("usage") or {}
            if tracker is not None:
                tracker.record(usage)
            return content, usage
        except (Timeout, ConnectionError, HTTPError) as exc:
            last_exc = exc
            if not _should_retry(exc, attempt, max_retries):
                raise
            wait = RETRY_BACKOFF_SEC * attempt
            reason = _retry_reason(exc)
            print(
                f"[retry] попытка {attempt}/{max_retries} не удалась ({reason}), "
                f"жду {wait:.0f}с…",
                flush=True,
            )
            time.sleep(wait)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("LLM: исчерпаны попытки")


def _parse_sse_delta(line: str) -> tuple[str | None, dict[str, Any] | None]:
    payload = line.removeprefix("data:").strip()
    if not payload or payload == "[DONE]":
        return None, None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None, None
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return None, usage
    choice = choices[0]
    if not isinstance(choice, dict):
        return None, usage
    delta = choice.get("delta")
    if isinstance(delta, dict):
        content = delta.get("content")
        if isinstance(content, str) and content:
            return content, usage
    message = choice.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str) and content:
            return content, usage
    return None, usage


def complete_stream(
    config: LlmConfig,
    messages: list[dict[str, str]],
    *,
    on_delta: Callable[[str], None] | None = None,
    tracker: UsageTracker | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    max_retries: int = MAX_RETRIES,
) -> tuple[str, dict[str, Any]]:
    for attempt in range(1, max_retries + 1):
        parts: list[str] = []
        usage: dict[str, Any] = {}
        try:
            response = requests.post(
                f"{config.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": config.model, "messages": messages, "stream": True},
                timeout=timeout,
                stream=True,
            )
            if response.status_code in RETRYABLE_HTTP:
                response.raise_for_status()
            response.raise_for_status()
            response.encoding = "utf-8"
            for raw_line in response.iter_lines(decode_unicode=False):
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8")
                chunk, chunk_usage = _parse_sse_delta(line)
                if chunk_usage:
                    usage = chunk_usage
                if chunk:
                    parts.append(chunk)
                    if on_delta is not None:
                        on_delta(chunk)
            content = "".join(parts)
            if not content:
                raise RuntimeError("LLM stream: пустой ответ")
            if tracker is not None:
                tracker.record(usage)
            return content, usage
        except (Timeout, ConnectionError, HTTPError, RuntimeError) as exc:
            if not _should_retry(exc, attempt, max_retries):
                break
            wait = RETRY_BACKOFF_SEC * attempt
            reason = _retry_reason(exc)
            print(
                f"[retry] попытка {attempt}/{max_retries} не удалась ({reason}), "
                f"жду {wait:.0f}с…",
                flush=True,
            )
            time.sleep(wait)
    print("[stream] fallback to complete", flush=True)
    content, usage = complete(
        config,
        messages,
        tracker=tracker,
        timeout=timeout,
        max_retries=1,
    )
    if on_delta is not None and content:
        on_delta(content)
    return content, usage
