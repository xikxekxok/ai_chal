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

DEFAULT_MODEL = "deepseek/deepseek-v3.2"
DEFAULT_TIMEOUT = 45
MAX_RETRIES = 4
RETRYABLE_HTTP = frozenset({429, 502, 503, 504})


@dataclass
class LlmConfig:
    api_key: str
    base_url: str
    model: str
    timeout: int = DEFAULT_TIMEOUT


def load_llm_config() -> LlmConfig:
    api_key = os.environ.get("DOCKHOST_AI_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print(
            "[error] Задайте DOCKHOST_AI_KEY в .env в корне репозитория.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return LlmConfig(
        api_key=api_key,
        base_url=os.environ.get("OPENAI_BASE_URL", "https://inference.dockhost.io/v1").rstrip("/"),
        model=os.environ.get("DOCKHOST_MODEL", DEFAULT_MODEL),
    )


def _retry_reason(exc: BaseException) -> str:
    if isinstance(exc, Timeout):
        return "таймаут"
    if isinstance(exc, ConnectionError):
        return "сеть"
    if isinstance(exc, HTTPError) and exc.response is not None:
        return f"HTTP {exc.response.status_code}"
    return type(exc).__name__


def _should_retry(exc: BaseException, attempt: int) -> bool:
    if attempt >= MAX_RETRIES:
        return False
    if isinstance(exc, (Timeout, ConnectionError)):
        return True
    if isinstance(exc, HTTPError) and exc.response is not None:
        return exc.response.status_code in RETRYABLE_HTTP
    return False


def complete_message(
    config: LlmConfig,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.2,
) -> tuple[dict[str, Any], dict[str, int]]:
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    last_exc: BaseException | None = None
    waits = {1: 2, 2: 4, 3: 6}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(
                f"{config.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=config.timeout,
            )
            response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]
            usage = data.get("usage") or {}
            return message, {
                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "completion_tokens": int(usage.get("completion_tokens") or 0),
            }
        except (Timeout, ConnectionError, HTTPError) as exc:
            last_exc = exc
            if not _should_retry(exc, attempt):
                raise
            wait = waits.get(attempt, 6)
            print(
                f"[retry] попытка {attempt}/{MAX_RETRIES} не удалась "
                f"({_retry_reason(exc)}), жду {wait}с...",
                flush=True,
            )
            time.sleep(wait)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("LLM request failed")
