"""Retrieve top-k чанков по cosine similarity."""

from __future__ import annotations

import math
from typing import Any

from embeddings import embed_text


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def retrieve(
    question: str,
    chunks: list[dict[str, Any]],
    *,
    top_k: int = 4,
) -> list[dict[str, Any]]:
    query_vec = embed_text(question)
    scored: list[tuple[float, dict[str, Any]]] = []
    for chunk in chunks:
        embedding = chunk.get("embedding")
        if not isinstance(embedding, list):
            continue
        score = cosine_similarity(query_vec, embedding)
        scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    results: list[dict[str, Any]] = []
    for score, chunk in scored[:top_k]:
        meta = chunk.get("meta") or {}
        results.append(
            {
                "score": score,
                "chunk_id": meta.get("chunk_id"),
                "path": meta.get("path"),
                "text": chunk.get("text") or "",
            }
        )
    return results


def print_hits(hits: list[dict[str, Any]]) -> None:
    print(f"[rag] top-{len(hits)}:")
    for hit in hits:
        print(
            f"  path={hit.get('path')} "
            f"chunk={hit.get('chunk_id')} "
            f"score={hit.get('score', 0):.4f}"
        )
