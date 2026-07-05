from __future__ import annotations

import math
from typing import Any

from embeddings import embed_text
from history import SessionState


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _chunk_to_hit(chunk: dict[str, Any], *, score: float = 0.0) -> dict[str, Any]:
    meta = chunk.get("meta") or {}
    return {
        "score": score,
        "chunk_id": meta.get("chunk_id"),
        "source_id": meta.get("source_id"),
        "title": meta.get("title"),
        "section": meta.get("section"),
        "text": chunk.get("text", ""),
    }


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
    return [_chunk_to_hit(chunk, score=score) for score, chunk in scored[:top_k]]


def fetch_chunks_by_id(
    chunk_ids: list[str],
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not chunk_ids:
        return []
    wanted = {chunk_id for chunk_id in chunk_ids if chunk_id}
    if not wanted:
        return []
    by_id: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        meta = chunk.get("meta") or {}
        chunk_id = meta.get("chunk_id")
        if chunk_id in wanted and chunk_id not in by_id:
            by_id[str(chunk_id)] = chunk
    results: list[dict[str, Any]] = []
    for chunk_id in chunk_ids:
        chunk = by_id.get(chunk_id)
        if chunk is not None:
            results.append(_chunk_to_hit(chunk, score=0.0))
    return results


def _parse_chunk_index(chunk_id: str) -> tuple[str, int] | None:
    if ":" not in chunk_id:
        return None
    source_id, index_raw = chunk_id.rsplit(":", 1)
    if not source_id or not index_raw.isdigit():
        return None
    return source_id, int(index_raw)


def _build_source_index(chunks: list[dict[str, Any]]) -> dict[str, dict[int, dict[str, Any]]]:
    by_source: dict[str, dict[int, dict[str, Any]]] = {}
    for chunk in chunks:
        meta = chunk.get("meta") or {}
        chunk_id = str(meta.get("chunk_id", ""))
        parsed = _parse_chunk_index(chunk_id)
        if parsed is None:
            continue
        source_id, index = parsed
        by_source.setdefault(source_id, {})[index] = chunk
    return by_source


def expand_neighbor_chunks(
    hits: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    *,
    seed_hits: list[dict[str, Any]] | None = None,
    radius: int = 1,
    max_added: int = 8,
) -> tuple[list[dict[str, Any]], int]:
    if not hits or max_added <= 0:
        return hits, 0

    by_source = _build_source_index(chunks)
    present = {str(hit.get("chunk_id")) for hit in hits if hit.get("chunk_id")}
    seeds = seed_hits if seed_hits is not None else hits
    added: list[dict[str, Any]] = []

    for hit in seeds:
        chunk_id = str(hit.get("chunk_id", ""))
        parsed = _parse_chunk_index(chunk_id)
        if parsed is None:
            continue
        source_id, index = parsed
        source_chunks = by_source.get(source_id)
        if not source_chunks:
            continue
        for offset in range(-radius, radius + 1):
            if offset == 0:
                continue
            neighbor = source_chunks.get(index + offset)
            if neighbor is None:
                continue
            meta = neighbor.get("meta") or {}
            neighbor_id = str(meta.get("chunk_id", ""))
            if not neighbor_id or neighbor_id in present:
                continue
            present.add(neighbor_id)
            added.append(_chunk_to_hit(neighbor, score=0.0))
            if len(added) >= max_added:
                return hits + added, len(added)

    return hits + added, len(added)


def sticky_chunk_ids(session: SessionState) -> list[str]:
    if session.recent_chunk_ids:
        return list(session.recent_chunk_ids)
    return list(session.last_chunk_ids)


def dedupe_by_chunk_id(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for hit in hits:
        chunk_id = hit.get("chunk_id")
        if not chunk_id or chunk_id in seen:
            continue
        seen.add(str(chunk_id))
        unique.append(hit)
    return unique


def format_fusion_stats(stats: dict[str, int]) -> str:
    neighbors = stats.get("neighbors", 0)
    base = (
        f"primary={stats['primary']} secondary={stats['secondary']} "
        f"sticky={stats['sticky']} fused={stats['fused']} unique={stats['unique']}"
    )
    if neighbors:
        return f"{base} neighbors={neighbors}"
    return base


def retrieve_fusion(
    standalone_query_en: str,
    *,
    is_follow_up: bool,
    use_sticky: bool = True,
    session: SessionState,
    chunks: list[dict[str, Any]],
    primary_k: int = 20,
    secondary_k: int = 10,
    expand_neighbors: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    primary = retrieve(standalone_query_en, chunks, top_k=primary_k)
    secondary: list[dict[str, Any]] = []
    sticky: list[dict[str, Any]] = []
    sticky_ids = sticky_chunk_ids(session)

    use_fusion = is_follow_up and use_sticky and (
        bool(session.last_standalone_query_en) or bool(sticky_ids)
    )
    if use_fusion:
        if session.last_standalone_query_en:
            secondary = retrieve(session.last_standalone_query_en, chunks, top_k=secondary_k)
        if sticky_ids:
            sticky = fetch_chunks_by_id(sticky_ids, chunks)

    merged = primary + secondary + sticky
    fused = dedupe_by_chunk_id(merged)
    neighbors_added = 0
    if expand_neighbors and fused:
        seed_hits = sticky + primary[:3]
        fused, neighbors_added = expand_neighbor_chunks(
            fused,
            chunks,
            seed_hits=seed_hits,
            max_added=8,
        )
        fused = dedupe_by_chunk_id(fused)

    stats = {
        "primary": len(primary),
        "secondary": len(secondary),
        "sticky": len(sticky),
        "fused": len(merged),
        "unique": len(fused),
        "neighbors": neighbors_added,
    }
    return fused, stats
