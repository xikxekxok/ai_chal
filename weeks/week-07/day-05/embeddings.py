"""Эмбеддинги через Ollama (nomic-embed-text) + pack/unpack float32."""

from __future__ import annotations

import os
import struct
from collections.abc import Sequence

import requests

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "nomic-embed-text"


class OllamaUnavailableError(RuntimeError):
    """Ollama недоступен или вернул ошибку."""


def base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def model_name() -> str:
    return os.environ.get("OLLAMA_EMBED_MODEL", DEFAULT_MODEL)


def is_available(*, timeout: float = 3.0) -> bool:
    try:
        response = requests.get(f"{base_url()}/api/tags", timeout=timeout)
        response.raise_for_status()
        return True
    except requests.RequestException:
        return False


def embed_text(text: str, *, timeout: int = 120) -> list[float]:
    try:
        response = requests.post(
            f"{base_url()}/api/embeddings",
            json={"model": model_name(), "prompt": text},
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise OllamaUnavailableError(f"Ollama embed failed: {exc}") from exc

    embedding = response.json().get("embedding")
    if not isinstance(embedding, list) or not embedding:
        raise OllamaUnavailableError("Ollama вернул ответ без embedding")
    return [float(x) for x in embedding]


def pack_embedding(vec: Sequence[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def unpack_embedding(blob: bytes | memoryview | None) -> list[float] | None:
    if blob is None:
        return None
    data = bytes(blob)
    if len(data) < 4 or len(data) % 4 != 0:
        return None
    n = len(data) // 4
    return list(struct.unpack(f"<{n}f", data))
