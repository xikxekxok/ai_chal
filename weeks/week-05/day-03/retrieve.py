from __future__ import annotations

import math
from typing import Any

from embeddings import embed_text


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def retrieve(
    question_en: str,
    chunks: list[dict[str, Any]],
    *,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    query_vec = embed_text(question_en)
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
                "source_id": meta.get("source_id"),
                "title": meta.get("title"),
                "section": meta.get("section"),
                "text": chunk.get("text", ""),
            }
        )
    return results


def format_retrieve_results(results: list[dict[str, Any]]) -> str:
    lines = [f"top-{len(results)}:"]
    for item in results:
        lines.append(
            f"  chunk_id={item.get('chunk_id')} "
            f"source_id={item.get('source_id')} "
            f"score={item.get('score', 0):.4f}"
        )
        lines.append(f"    title={item.get('title')!r} section={item.get('section')!r}")
    return "\n".join(lines)
