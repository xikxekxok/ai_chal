"""Индексация документации project/ для RAG."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from embeddings import check_ollama, embed_text, model_name
from paths import DATA_DIR, INDEX_PATH, PROJECT_DIR

CHUNK_CHARS = 1000
OVERLAP_CHARS = 150
DOC_GLOBS = ("**/*.md", "**/*.yaml", "**/*.yml")


def _iter_doc_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for pattern in DOC_GLOBS:
        files.extend(root.glob(pattern))
    return sorted({p.resolve() for p in files if p.is_file()})


def _chunk_text(text: str, *, chunk_chars: int, overlap_chars: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_chars, len(text))
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(0, end - overlap_chars)
    return chunks


def load_index(path: Path = INDEX_PATH) -> dict[str, Any]:
    if not path.is_file():
        msg = f"Индекс не найден: {path}. Сначала: python …/main.py --index"
        raise FileNotFoundError(msg)
    return json.loads(path.read_text(encoding="utf-8"))


def build_index(
    *,
    project_dir: Path = PROJECT_DIR,
    index_path: Path = INDEX_PATH,
) -> dict[str, Any]:
    check_ollama()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    files = _iter_doc_files(project_dir)
    chunks: list[dict[str, Any]] = []
    chunk_id = 0
    for path in files:
        rel = path.relative_to(project_dir).as_posix()
        text = path.read_text(encoding="utf-8")
        for part in _chunk_text(text, chunk_chars=CHUNK_CHARS, overlap_chars=OVERLAP_CHARS):
            chunk_id += 1
            print(f"[index] embed {rel} chunk={chunk_id} chars={len(part)}", flush=True)
            chunks.append(
                {
                    "text": part,
                    "embedding": embed_text(part),
                    "meta": {
                        "chunk_id": chunk_id,
                        "path": rel,
                        "char_count": len(part),
                    },
                }
            )
    index: dict[str, Any] = {
        "version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "project_dir": str(project_dir),
        "embedding": {"provider": "ollama", "model": model_name()},
        "chunking": {
            "chunk_chars": CHUNK_CHARS,
            "overlap_chars": OVERLAP_CHARS,
        },
        "stats": {"files": len(files), "chunks": len(chunks)},
        "files": [p.relative_to(project_dir).as_posix() for p in files],
        "chunks": chunks,
    }
    index_path.write_text(
        json.dumps(index, ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        f"[index] saved {index_path} files={len(files)} chunks={len(chunks)}",
        flush=True,
    )
    return index


def ensure_index(*, rebuild: bool = False) -> dict[str, Any]:
    if rebuild or not INDEX_PATH.is_file():
        return build_index()
    return load_index()


def show_index_summary(index: dict[str, Any] | None = None) -> None:
    data = index if index is not None else load_index()
    stats = data.get("stats") or {}
    print(f"[index] files={stats.get('files')} chunks={stats.get('chunks')}")
    print(f"[index] created_at={data.get('created_at')}")
    print(f"[index] embedding={data.get('embedding')}")
    for path in data.get("files") or []:
        print(f"  - {path}")
