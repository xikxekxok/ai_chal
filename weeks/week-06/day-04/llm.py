"""Локальная (Ollama) и облачная (Dockhost) генерация."""

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

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen3:4b"
LOCAL_TIMEOUT = 300

DEFAULT_CLOUD_MODEL = "deepseek/deepseek-v3.2"
CLOUD_TIMEOUT = 45
MAX_RETRIES = 4
RETRY_BACKOFF_SEC = 2.0
RETRYABLE_HTTP = frozenset({429, 502, 503, 504})


@dataclass(frozen=True)
class GenOptions:
    temperature: float | None = None
    num_ctx: int | None = None


@dataclass
class OllamaConfig:
    base_url: str
    model: str


@dataclass
class CompletionResult:
    content: str
    usage: dict[str, Any]
    latency_ms: int
    thinking: str = ""


@dataclass
class StreamResult:
    thinking: str
    content: str
    usage: dict[str, Any]
    latency_ms: int


def load_ollama_config(*, model: str | None = None) -> OllamaConfig:
    return OllamaConfig(
        base_url=os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL).rstrip("/"),
        model=model or os.environ.get("OLLAMA_CHAT_MODEL", DEFAULT_OLLAMA_MODEL),
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


def _model_present(model_names: set[str], model: str) -> bool:
    return model in model_names or f"{model}:latest" in model_names


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
    if not _model_present(model_names, cfg.model):
        print(
            f"[error] Модель {cfg.model} не найдена. Выполните: ollama pull {cfg.model}",
            file=sys.stderr,
        )
        sys.exit(1)

    embed_model = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    if not _model_present(model_names, embed_model):
        print(
            f"[error] Модель {embed_model} не найдена. Выполните: ollama pull {embed_model}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"[check] server: {cfg.base_url} OK")
    print(f"[check] model: {cfg.model} OK (think=on, stream)")
    print(f"[check] embed: {embed_model} OK")


def _build_local_payload(
    cfg: OllamaConfig,
    messages: list[dict[str, str]],
    gen: GenOptions,
    *,
    stream: bool = False,
    think: bool = True,
) -> dict[str, Any]:
    """Native /api/chat — think=true разделяет thinking и content при stream."""
    payload: dict[str, Any] = {
        "model": cfg.model,
        "messages": messages,
        "stream": stream,
        "think": think,
    }
    options: dict[str, Any] = {}
    if gen.temperature is not None:
        options["temperature"] = gen.temperature
    if gen.num_ctx is not None:
        options["num_ctx"] = gen.num_ctx
    if options:
        payload["options"] = options
    return payload


def _usage_from_chat_response(data: dict[str, Any]) -> dict[str, int]:
    prompt = int(data.get("prompt_eval_count") or 0)
    completion = int(data.get("eval_count") or 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }


def stream_local(
    messages: list[dict[str, str]],
    *,
    config: OllamaConfig | None = None,
    gen: GenOptions | None = None,
    on_thinking: Callable[[str], None] | None = None,
    on_content: Callable[[str], None] | None = None,
) -> StreamResult:
    cfg = config or load_ollama_config()
    opts = gen or GenOptions()
    start = time.perf_counter()
    thinking_parts: list[str] = []
    content_parts: list[str] = []
    usage: dict[str, Any] = {}

    try:
        response = requests.post(
            f"{cfg.base_url}/api/chat",
            json=_build_local_payload(cfg, messages, opts, stream=True, think=True),
            timeout=LOCAL_TIMEOUT,
            stream=True,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"[error] запрос к Ollama не удался: {exc}", file=sys.stderr)
        sys.exit(1)

    for raw_line in response.iter_lines(decode_unicode=True):
        if not raw_line:
            continue
        try:
            chunk = json.loads(raw_line)
        except json.JSONDecodeError:
            continue

        message = chunk.get("message") or {}
        thinking_delta = message.get("thinking") or ""
        content_delta = message.get("content") or ""

        if thinking_delta:
            thinking_parts.append(thinking_delta)
            if on_thinking is not None:
                on_thinking(thinking_delta)
        if content_delta:
            content_parts.append(content_delta)
            if on_content is not None:
                on_content(content_delta)

        if chunk.get("done"):
            usage = _usage_from_chat_response(chunk)

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    thinking = "".join(thinking_parts)
    content = "".join(content_parts).strip()
    if not content:
        print("[error] локальная LLM вернула пустой ответ.", file=sys.stderr)
        if thinking:
            print(
                "[error] reasoning завершился, но content пуст.",
                file=sys.stderr,
            )
        sys.exit(1)

    return StreamResult(
        thinking=thinking,
        content=content,
        usage=usage,
        latency_ms=elapsed_ms,
    )


def complete_local(
    messages: list[dict[str, str]],
    *,
    config: OllamaConfig | None = None,
    gen: GenOptions | None = None,
) -> CompletionResult:
    result = stream_local(messages, config=config, gen=gen)
    return CompletionResult(
        content=result.content,
        usage=result.usage,
        latency_ms=result.latency_ms,
        thinking=result.thinking,
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
