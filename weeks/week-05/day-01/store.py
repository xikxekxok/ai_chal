from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from chunking import chunking_config
from embeddings import embedding_config
from paths import INDEX_PATH
from sources import BOOKS


def index_exists() -> bool:
    return INDEX_PATH.is_file()


def load_index() -> dict[str, Any] | None:
    if not index_exists():
        return None
    with INDEX_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_index(data: dict[str, Any]) -> None:
    required_root = (
        "version",
        "corpus",
        "created_at",
        "chunking",
        "embedding",
        "stats",
        "sources",
        "chunks",
    )
    for key in required_root:
        if key not in data:
            msg = f"index missing key: {key}"
            raise ValueError(msg)


def build_sources() -> list[dict[str, str]]:
    return [
        {
            "id": book.id,
            "title": book.title,
            "author": book.author,
            "file": book.filename,
        }
        for book in BOOKS
    ]


def build_index(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    total_chars = sum(chunk["meta"]["char_count"] for chunk in chunks)
    chunk_count = len(chunks)
    avg_chars = int(total_chars / chunk_count) if chunk_count else 0
    return {
        "version": 1,
        "corpus": "opossums",
        "created_at": datetime.now(UTC).isoformat(),
        "chunking": chunking_config(),
        "embedding": embedding_config(),
        "stats": {
            "books": len(BOOKS),
            "chunks": chunk_count,
            "avg_chars": avg_chars,
            "total_chars": total_chars,
        },
        "sources": build_sources(),
        "chunks": chunks,
    }


def save_index(data: dict[str, Any]) -> None:
    validate_index(data)
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=INDEX_PATH.parent,
        delete=False,
        suffix=".tmp",
    ) as handle:
        json.dump(data, handle, ensure_ascii=False)
        temp_path = Path(handle.name)
    temp_path.replace(INDEX_PATH)


def clear_index() -> bool:
    if not index_exists():
        return False
    INDEX_PATH.unlink()
    return True


def format_size_mb(path: Path) -> str:
    size = path.stat().st_size
    return f"{size / (1024 * 1024):.1f} MB"
