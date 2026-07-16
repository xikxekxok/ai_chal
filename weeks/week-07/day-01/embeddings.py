"""Эмбеддинги через Ollama (nomic-embed-text)."""

from __future__ import annotations

import os
import sys

import requests

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "nomic-embed-text"


def base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def model_name() -> str:
    return os.environ.get("OLLAMA_EMBED_MODEL", DEFAULT_MODEL)


def check_ollama() -> None:
    url = base_url()
    try:
        response = requests.get(f"{url}/api/tags", timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(
            f"[error] Ollama недоступен ({url}): {exc}. "
            "Запустите ollama serve и выполните: ollama pull nomic-embed-text",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


def embed_text(text: str) -> list[float]:
    response = requests.post(
        f"{base_url()}/api/embeddings",
        json={"model": model_name(), "prompt": text},
        timeout=120,
    )
    response.raise_for_status()
    embedding = response.json().get("embedding")
    if not isinstance(embedding, list):
        msg = "Ollama вернул ответ без embedding"
        raise RuntimeError(msg)
    return embedding
