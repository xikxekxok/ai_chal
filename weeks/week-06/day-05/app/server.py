"""FastAPI: REST API + SSE stream + статика Alpine.js игры."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import OPPOSSUM_JOKE_THEMES, AppConfig, load_config
from app.limits import RateLimiter, ensure_system_prompt, trim_messages
from app.llm import (
    CloudError,
    LLMError,
    OllamaError,
    Provider,
    check_cloud_status,
    check_ollama_status,
    complete_chat,
    iter_chat_stream,
)

ChatRole = Literal["system", "user", "assistant"]


class ChatMessage(BaseModel):
    role: ChatRole
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    provider: Provider = "local"


class ChatResponse(BaseModel):
    reply: str
    thinking: str
    latency_ms: int
    usage: dict[str, object]
    trimmed: bool
    provider: Provider


def _sse(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _prepare_messages(body: ChatRequest, cfg: AppConfig) -> tuple[list[dict[str, str]], bool]:
    raw_messages = [m.model_dump() for m in body.messages]
    with_system = ensure_system_prompt(raw_messages, cfg.system_prompt)
    return trim_messages(with_system, cfg)


def _ensure_provider_available(provider: Provider, cfg: AppConfig) -> None:
    if provider == "cloud":
        if not check_cloud_status(cfg).get("ok"):
            raise HTTPException(status_code=502, detail="Cloud LLM unavailable")
        return
    if not check_ollama_status(cfg).get("ok"):
        raise HTTPException(status_code=502, detail="Local Ollama unavailable")


def create_app(config: AppConfig | None = None) -> FastAPI:
    cfg = config or load_config()
    limiter = RateLimiter(cfg.rate_limit_per_min)
    app = FastAPI(title="Opossum Jokes", version="1.0.0")

    static_dir = cfg.static_dir
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/api/health")
    def health() -> dict[str, object]:
        local = check_ollama_status(cfg)
        cloud = check_cloud_status(cfg)
        return {
            "ok": bool(local.get("ok")) or bool(cloud.get("ok")),
            "app": "opossum-jokes",
            "local": local,
            "cloud": cloud,
            "stream": True,
            "think": True,
            "limits": {
                "rate_per_min": cfg.rate_limit_per_min,
                "max_messages": cfg.max_messages,
                "max_chars": cfg.max_chars,
                "cloud_max_tokens": cfg.max_tokens,
                "num_ctx": cfg.num_ctx,
                "ollama_max_predict": cfg.ollama_max_predict or None,
                "ollama_temperature": cfg.ollama_temperature,
            },
        }

    def _rate_limit_or_raise(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        if not limiter.allow(client_ip):
            retry_after = limiter.retry_after_sec(client_ip)
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Rate limit exceeded ({cfg.rate_limit_per_min}/min). "
                    f"Retry after {retry_after}s."
                ),
                headers={"Retry-After": str(retry_after)},
            )

    @app.get("/api/themes")
    def themes() -> dict[str, object]:
        return {"themes": OPPOSSUM_JOKE_THEMES}

    @app.post("/api/chat", response_model=ChatResponse)
    def chat(body: ChatRequest, request: Request) -> ChatResponse:
        _rate_limit_or_raise(request)
        _ensure_provider_available(body.provider, cfg)

        trimmed_messages, was_trimmed = _prepare_messages(body, cfg)
        try:
            result = complete_chat(trimmed_messages, provider=body.provider, config=cfg)
        except OllamaError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except CloudError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except LLMError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        return ChatResponse(
            reply=result.content,
            thinking=result.thinking,
            latency_ms=result.latency_ms,
            usage=result.usage,
            trimmed=was_trimmed,
            provider=result.provider,
        )

    @app.post("/api/chat/stream")
    def chat_stream(body: ChatRequest, request: Request) -> StreamingResponse:
        _rate_limit_or_raise(request)
        _ensure_provider_available(body.provider, cfg)

        trimmed_messages, was_trimmed = _prepare_messages(body, cfg)
        provider = body.provider

        def event_generator() -> Iterator[str]:
            try:
                for item in iter_chat_stream(trimmed_messages, provider=provider, config=cfg):
                    event = str(item.get("event") or "")
                    if event in {"thinking", "content"}:
                        yield _sse(event, {"delta": item.get("delta") or ""})
                    elif event == "done":
                        yield _sse(
                            "done",
                            {
                                "reply": item.get("reply") or "",
                                "thinking": item.get("thinking") or "",
                                "latency_ms": item.get("latency_ms") or 0,
                                "usage": item.get("usage") or {},
                                "trimmed": was_trimmed,
                                "provider": item.get("provider") or provider,
                            },
                        )
            except OllamaError as exc:
                yield _sse("error", {"detail": str(exc)})
            except CloudError as exc:
                yield _sse("error", {"detail": str(exc)})
            except LLMError as exc:
                yield _sse("error", {"detail": str(exc)})

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/")
    def index() -> FileResponse:
        index_path = static_dir / "index.html"
        if not index_path.is_file():
            raise HTTPException(status_code=404, detail="index.html not found")
        return FileResponse(index_path)

    return app


app = create_app()
