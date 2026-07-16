"""Dockhost Inference client with retry logic."""

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


def _find_env_file() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    direct_env = repo_root / ".env"
    if direct_env.exists():
        return direct_env

    git_meta = repo_root / ".git"
    if git_meta.is_file():
        content = git_meta.read_text(encoding="utf-8").strip()
        prefix = "gitdir: "
        if content.startswith(prefix):
            gitdir = Path(content[len(prefix) :]).resolve()
            main_root = gitdir.parents[2]
            fallback_env = main_root / ".env"
            if fallback_env.exists():
                return fallback_env

    return direct_env


load_dotenv(_find_env_file())

DEFAULT_MODEL = "deepseek/deepseek-v3.2"
DEFAULT_TIMEOUT = 45
MAX_RETRIES = 4
RETRYABLE_HTTP = frozenset({429, 502, 503, 504})


@dataclass(slots=True)
class LlmConfig:
    api_key: str
    base_url: str
    model: str


@dataclass(slots=True)
class UsageTracker:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0

    def record(self, usage: dict[str, Any]) -> None:
        self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self.completion_tokens += int(usage.get("completion_tokens") or 0)
        self.calls += 1


def load_llm_config() -> LlmConfig:
    api_key = os.environ.get("DOCKHOST_AI_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print(
            "[error] Set DOCKHOST_AI_KEY in repo root .env.",
            file=sys.stderr,
        )
        sys.exit(1)

    base_url = os.environ.get("OPENAI_BASE_URL", "https://inference.dockhost.io/v1")
    model = os.environ.get("DOCKHOST_MODEL", DEFAULT_MODEL)
    return LlmConfig(api_key=api_key, base_url=base_url.rstrip("/"), model=model)


def _should_retry(exc: BaseException, attempt: int) -> bool:
    if attempt >= MAX_RETRIES:
        return False
    if isinstance(exc, (Timeout, ConnectionError)):
        return True
    if isinstance(exc, HTTPError) and exc.response is not None:
        return exc.response.status_code in RETRYABLE_HTTP
    return False


def _retry_reason(exc: BaseException) -> str:
    if isinstance(exc, Timeout):
        return "timeout"
    if isinstance(exc, ConnectionError):
        return "network"
    if isinstance(exc, HTTPError) and exc.response is not None:
        return f"HTTP {exc.response.status_code}"
    return type(exc).__name__


def complete(
    config: LlmConfig,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    tracker: UsageTracker | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
    }
    if tools:
        payload["tools"] = tools

    last_exc: BaseException | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(
                f"{config.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]
            usage = data.get("usage") or {}
            if tracker is not None:
                tracker.record(usage)
            return message, usage
        except (Timeout, ConnectionError, HTTPError) as exc:
            last_exc = exc
            if not _should_retry(exc, attempt):
                raise
            wait_seconds = attempt * 2
            print(
                f"[retry] attempt {attempt}/{MAX_RETRIES} failed "
                f"({_retry_reason(exc)}), waiting {wait_seconds}s...",
                flush=True,
            )
            time.sleep(wait_seconds)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("LLM call failed without exception.")
