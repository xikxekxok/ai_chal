"""Локальная Ollama (stream + thinking) и облачная Dockhost (legacy)."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

import requests
from requests.exceptions import ConnectionError, HTTPError, Timeout

from app.config import AppConfig, load_config

Provider = Literal["local", "cloud"]

LOCAL_TIMEOUT = 300
CLOUD_TIMEOUT = 45
MAX_RETRIES = 4
RETRY_BACKOFF_SEC = 2.0
RETRYABLE_HTTP = frozenset({429, 502, 503, 504})


class LLMError(Exception):
    """Базовая ошибка генерации."""


class OllamaError(LLMError):
    """Ollama недоступен или вернул ошибку."""


class CloudError(LLMError):
    """Dockhost / облако недоступно или вернуло ошибку."""


@dataclass
class CompletionResult:
    content: str
    usage: dict[str, Any]
    latency_ms: int
    provider: Provider
    thinking: str = ""


@dataclass
class StreamResult:
    thinking: str
    content: str
    usage: dict[str, Any]
    latency_ms: int


def _model_present(model_names: set[str], model: str) -> bool:
    return model in model_names or f"{model}:latest" in model_names


def check_ollama_status(config: AppConfig | None = None) -> dict[str, object]:
    cfg = config or load_config()
    try:
        response = requests.get(f"{cfg.ollama_base_url}/api/tags", timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        return {
            "ok": False,
            "error": f"Ollama недоступен на {cfg.ollama_base_url}: {exc}",
            "model": cfg.ollama_model,
        }

    tags = response.json().get("models", [])
    model_names = {item.get("name", "") for item in tags}
    if not _model_present(model_names, cfg.ollama_model):
        return {
            "ok": False,
            "error": (
                f"Модель {cfg.ollama_model} не найдена. "
                f"Выполните: ollama pull {cfg.ollama_model}"
            ),
            "model": cfg.ollama_model,
        }

    return {
        "ok": True,
        "model": cfg.ollama_model,
        "ollama_url": cfg.ollama_base_url,
    }


def check_cloud_status(config: AppConfig | None = None) -> dict[str, object]:
    cfg = config or load_config()
    if not cfg.cloud_api_key:
        return {
            "ok": False,
            "error": "DOCKHOST_AI_KEY не задан (см. .env.example).",
            "model": cfg.cloud_model,
        }
    return {
        "ok": True,
        "model": cfg.cloud_model,
        "base_url": cfg.cloud_base_url,
    }


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


def _usage_from_chat_response(data: dict[str, Any]) -> dict[str, int]:
    prompt = int(data.get("prompt_eval_count") or 0)
    completion = int(data.get("eval_count") or 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }


def _build_local_payload(
    cfg: AppConfig,
    messages: list[dict[str, str]],
    *,
    think: bool = True,
) -> dict[str, Any]:
    """Native /api/chat — num_predict не задаём (как day-04): qwen3 тратит budget на thinking."""
    payload: dict[str, Any] = {
        "model": cfg.ollama_model,
        "messages": messages,
        "stream": True,
        "think": think,
        "options": {"num_ctx": cfg.num_ctx, "temperature": cfg.ollama_temperature},
    }
    if cfg.ollama_max_predict > 0:
        payload["options"]["num_predict"] = cfg.ollama_max_predict
    return payload


def iter_local_stream(
    messages: list[dict[str, str]],
    config: AppConfig | None = None,
    *,
    think: bool = True,
    _retried: bool = False,
) -> Iterator[dict[str, object]]:
    """Yields SSE-ready dicts: thinking/content deltas and final done metadata."""
    cfg = config or load_config()
    start = time.perf_counter()
    thinking_parts: list[str] = []
    content_parts: list[str] = []
    usage: dict[str, Any] = {}

    try:
        response = requests.post(
            f"{cfg.ollama_base_url}/api/chat",
            json=_build_local_payload(cfg, messages, think=think),
            timeout=LOCAL_TIMEOUT,
            stream=True,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise OllamaError(f"запрос к Ollama не удался: {exc}") from exc

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
            yield {"event": "thinking", "delta": thinking_delta}
        if content_delta:
            content_parts.append(content_delta)
            yield {"event": "content", "delta": content_delta}

        if chunk.get("done"):
            usage = _usage_from_chat_response(chunk)

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    thinking = "".join(thinking_parts)
    content = "".join(content_parts).strip()
    if not content:
        if think and not _retried:
            yield from iter_local_stream(messages, config, think=False, _retried=True)
            return
        detail = "LLM вернул пустой ответ"
        if thinking:
            detail += (
                " (reasoning завершился, content пуст — проверьте num_ctx / ollama_max_predict)"
            )
        raise OllamaError(detail)

    yield {
        "event": "done",
        "reply": content,
        "thinking": thinking,
        "usage": usage,
        "latency_ms": elapsed_ms,
        "provider": "local",
    }


def stream_local(
    messages: list[dict[str, str]],
    config: AppConfig | None = None,
) -> StreamResult:
    thinking = ""
    content = ""
    usage: dict[str, Any] = {}
    latency_ms = 0
    for item in iter_local_stream(messages, config):
        event = item.get("event")
        if event == "thinking":
            thinking += str(item.get("delta") or "")
        elif event == "content":
            content += str(item.get("delta") or "")
        elif event == "done":
            content = str(item.get("reply") or content)
            thinking = str(item.get("thinking") or thinking)
            usage = item.get("usage") or {}
            latency_ms = int(item.get("latency_ms") or 0)
    return StreamResult(
        thinking=thinking,
        content=content,
        usage=usage,
        latency_ms=latency_ms,
    )


def complete_local(
    messages: list[dict[str, str]],
    config: AppConfig | None = None,
) -> CompletionResult:
    result = stream_local(messages, config)
    return CompletionResult(
        content=result.content,
        usage=result.usage,
        latency_ms=result.latency_ms,
        provider="local",
        thinking=result.thinking,
    )


def complete_cloud(
    messages: list[dict[str, str]],
    config: AppConfig | None = None,
) -> CompletionResult:
    result = stream_cloud(messages, config)
    return CompletionResult(
        content=result.content,
        usage=result.usage,
        latency_ms=result.latency_ms,
        provider="cloud",
        thinking=result.thinking,
    )


def _cloud_headers(cfg: AppConfig) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {cfg.cloud_api_key}",
        "Content-Type": "application/json",
    }


def _parse_openai_sse_line(raw_line: str) -> dict[str, Any] | None:
    line = raw_line.strip()
    if not line.startswith("data:"):
        return None
    payload = line[5:].strip()
    if payload == "[DONE]":
        return {"done": True}
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def iter_cloud_stream(
    messages: list[dict[str, str]],
    config: AppConfig | None = None,
) -> Iterator[dict[str, object]]:
    """Yields SSE-ready dicts: content deltas and final done metadata."""
    cfg = config or load_config()
    if not cfg.cloud_api_key:
        raise CloudError("DOCKHOST_AI_KEY не задан")

    payload: dict[str, object] = {
        "model": cfg.cloud_model,
        "messages": messages,
        "max_tokens": cfg.max_tokens,
        "stream": True,
    }
    start = time.perf_counter()
    content_parts: list[str] = []
    usage: dict[str, Any] = {}
    last_exc: BaseException | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        content_parts.clear()
        usage = {}
        try:
            response = requests.post(
                f"{cfg.cloud_base_url}/chat/completions",
                headers=_cloud_headers(cfg),
                json=payload,
                timeout=CLOUD_TIMEOUT,
                stream=True,
            )
            if response.status_code in RETRYABLE_HTTP:
                response.raise_for_status()
            response.raise_for_status()
        except (Timeout, ConnectionError, HTTPError) as exc:
            last_exc = exc
            if not _should_retry(exc, attempt, MAX_RETRIES):
                break
            time.sleep(RETRY_BACKOFF_SEC * attempt)
            continue

        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            chunk = _parse_openai_sse_line(raw_line)
            if chunk is None:
                continue
            if chunk.get("done"):
                break

            choices = chunk.get("choices") or []
            if not choices:
                continue
            choice = choices[0]
            delta = (choice.get("delta") or {}).get("content") or ""
            if delta:
                content_parts.append(delta)
                yield {"event": "content", "delta": delta}
            if chunk.get("usage"):
                usage = chunk["usage"]

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        content = "".join(content_parts).strip()
        if not content:
            raise CloudError("облачная LLM вернула пустой ответ")

        yield {
            "event": "done",
            "reply": content,
            "thinking": "",
            "usage": usage,
            "latency_ms": elapsed_ms,
            "provider": "cloud",
        }
        return

    reason = _retry_reason(last_exc) if last_exc else "unknown"
    raise CloudError(f"запрос к Dockhost не удался: {reason}") from last_exc


def stream_cloud(
    messages: list[dict[str, str]],
    config: AppConfig | None = None,
) -> StreamResult:
    content = ""
    usage: dict[str, Any] = {}
    latency_ms = 0
    for item in iter_cloud_stream(messages, config):
        event = item.get("event")
        if event == "content":
            content += str(item.get("delta") or "")
        elif event == "done":
            content = str(item.get("reply") or content)
            usage = item.get("usage") or {}
            latency_ms = int(item.get("latency_ms") or 0)
    return StreamResult(
        thinking="",
        content=content,
        usage=usage,
        latency_ms=latency_ms,
    )


def _complete_cloud_non_stream(
    messages: list[dict[str, str]],
    config: AppConfig | None = None,
) -> CompletionResult:
    cfg = config or load_config()
    if not cfg.cloud_api_key:
        raise CloudError("DOCKHOST_AI_KEY не задан")

    payload: dict[str, object] = {
        "model": cfg.cloud_model,
        "messages": messages,
        "max_tokens": cfg.max_tokens,
    }
    last_exc: BaseException | None = None
    start = time.perf_counter()
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(
                f"{cfg.cloud_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {cfg.cloud_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=CLOUD_TIMEOUT,
            )
            if response.status_code in RETRYABLE_HTTP:
                response.raise_for_status()
            response.raise_for_status()
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            data = response.json()
            content = data["choices"][0]["message"].get("content") or ""
            if not content:
                raise CloudError("облачная LLM вернула пустой ответ")
            return CompletionResult(
                content=content,
                usage=data.get("usage") or {},
                latency_ms=elapsed_ms,
                provider="cloud",
            )
        except (Timeout, ConnectionError, HTTPError) as exc:
            last_exc = exc
            if not _should_retry(exc, attempt, MAX_RETRIES):
                break
            time.sleep(RETRY_BACKOFF_SEC * attempt)

    reason = _retry_reason(last_exc) if last_exc else "unknown"
    raise CloudError(f"запрос к Dockhost не удался: {reason}") from last_exc


def iter_chat_stream(
    messages: list[dict[str, str]],
    *,
    provider: Provider = "local",
    config: AppConfig | None = None,
) -> Iterator[dict[str, object]]:
    if provider == "cloud":
        yield from iter_cloud_stream(messages, config)
        return
    yield from iter_local_stream(messages, config)


def complete_chat(
    messages: list[dict[str, str]],
    *,
    provider: Provider = "local",
    config: AppConfig | None = None,
) -> CompletionResult:
    if provider == "cloud":
        return complete_cloud(messages, config)
    return complete_local(messages, config)
