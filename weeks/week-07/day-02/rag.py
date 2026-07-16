from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from paths import DATA_DIR, RAG_INDEX_PATH, REPO_ROOT

MAX_FILE_BYTES = 200_000
CHUNK_SIZE = 1600
CHUNK_OVERLAP = 200
TOKEN_RE = re.compile(r"[A-Za-zА-Яа-я0-9_./-]{3,}")
DOC_PATTERNS = ("README.md", "AGENTS.md", "*.mdc", "*.md", "*.py")
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "node_modules",
    "data",
    ".worktrees",
}
EXCLUDED_SUFFIXES = {".json", ".log", ".lock", ".sqlite", ".png", ".jpg", ".jpeg"}


@dataclass
class Chunk:
    path: str
    text: str
    tokens: list[str]


def _should_index(path: Path) -> bool:
    relative = path.relative_to(REPO_ROOT)
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    if path.suffix in EXCLUDED_SUFFIXES:
        return False
    if path.stat().st_size > MAX_FILE_BYTES:
        return False
    name = path.name
    return any(path.match(pattern) or name == pattern for pattern in DOC_PATTERNS)


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def _chunk_text(text: str) -> list[str]:
    if len(text) <= CHUNK_SIZE:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + CHUNK_SIZE)
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


def _build_index() -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if not _should_index(path):
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        relative = str(path.relative_to(REPO_ROOT))
        for chunk in _chunk_text(text):
            tokens = _tokenize(f"{relative}\n{chunk}")
            if not tokens:
                continue
            chunks.append(Chunk(path=relative, text=chunk.strip(), tokens=tokens))
    return chunks


def _load_cached_index() -> list[Chunk] | None:
    if not RAG_INDEX_PATH.exists():
        return None

    try:
        payload = json.loads(RAG_INDEX_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    chunks = [
        Chunk(
            path=item["path"],
            text=item["text"],
            tokens=item["tokens"],
        )
        for item in payload.get("chunks", [])
    ]
    return chunks or None


def _save_index(chunks: list[Chunk]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "chunks": [
            {
                "path": chunk.path,
                "text": chunk.text,
                "tokens": chunk.tokens,
            }
            for chunk in chunks
        ]
    }
    RAG_INDEX_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_index() -> list[Chunk]:
    cached = _load_cached_index()
    if cached is not None:
        print(f"[rag] loaded cached index with {len(cached)} chunks")
        return cached

    print("[rag] building local index...")
    chunks = _build_index()
    _save_index(chunks)
    print(f"[rag] indexed {len(chunks)} chunks")
    return chunks


def retrieve(
    chunks: list[Chunk],
    query: str,
    path_hints: list[str],
    limit: int = 6,
) -> list[Chunk]:
    query_tokens = _tokenize(query)
    scored: list[tuple[int, Chunk]] = []

    normalized_hints = [hint.lower() for hint in path_hints]
    for chunk in chunks:
        token_score = sum(chunk.tokens.count(token) for token in query_tokens)
        if token_score == 0:
            continue

        path_score = 0
        chunk_path_lower = chunk.path.lower()
        for hint in normalized_hints:
            if hint and hint in chunk_path_lower:
                path_score += 5

        score = token_score + path_score
        scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    top_chunks = [chunk for _, chunk in scored[:limit]]
    print(f"[rag] selected {len(top_chunks)} context chunks")
    return top_chunks
