"""Hybrid retrieve: FTS5 bm25 ∪ dense cosine → RRF fusion."""

from __future__ import annotations

import json
import math
import re
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any

from embeddings import OllamaUnavailableError, embed_text, is_available, unpack_embedding

RRF_K = 60
DEFAULT_TOP_M = 40


@dataclass
class ChunkHit:
    chunk_id: int
    note_id: int
    ord: int
    text: str
    title: str
    summary: str
    tags: list[str]
    rrf_score: float = 0.0
    fts_rank: int | None = None
    dense_rank: int | None = None
    dense_score: float | None = None


@dataclass
class RetrieveResult:
    hits: list[ChunkHit]
    mode: str  # hybrid | fts-only
    expand_terms: list[str] = field(default_factory=list)
    fts_count: int = 0
    dense_count: int = 0
    latency_ms: float = 0.0


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=True):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


_FTS_SPECIAL = re.compile(r"[^\w\u0400-\u04FF]+", re.UNICODE)


def build_fts_query(terms: list[str], fallback: str) -> str:
    """Build a safe FTS5 OR query from expand terms / raw question."""
    tokens: list[str] = []
    for term in terms:
        for tok in _FTS_SPECIAL.split(term.lower()):
            tok = tok.strip()
            if len(tok) >= 2:
                tokens.append(tok)
    if not tokens:
        for tok in _FTS_SPECIAL.split(fallback.lower()):
            tok = tok.strip()
            if len(tok) >= 2:
                tokens.append(tok)
    # unique preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    if not uniq:
        return '""'  # match nothing safely
    # quote tokens for phrase-safe matching; OR for recall
    return " OR ".join(f'"{t}"' for t in uniq[:24])


def fts_search(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = DEFAULT_TOP_M,
) -> list[dict[str, Any]]:
    fts_q = query.strip()
    if not fts_q or fts_q == '""':
        return []
    try:
        rows = conn.execute(
            """
            SELECT
                c.id AS chunk_id,
                c.note_id AS note_id,
                c.ord AS ord,
                c.text AS text,
                n.title AS title,
                n.summary AS summary,
                n.tags_json AS tags_json,
                bm25(chunks_fts) AS bm25
            FROM chunks_fts
            JOIN chunks c ON c.id = chunks_fts.rowid
            JOIN notes n ON n.id = c.note_id
            WHERE chunks_fts MATCH ?
            ORDER BY bm25(chunks_fts)
            LIMIT ?
            """,
            (fts_q, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []

    out: list[dict[str, Any]] = []
    for rank, row in enumerate(rows, start=1):
        tags = json.loads(row["tags_json"] or "[]")
        out.append(
            {
                "chunk_id": int(row["chunk_id"]),
                "note_id": int(row["note_id"]),
                "ord": int(row["ord"]),
                "text": str(row["text"]),
                "title": str(row["title"]),
                "summary": str(row["summary"] or ""),
                "tags": tags,
                "fts_rank": rank,
                "bm25": float(row["bm25"]),
            }
        )
    return out


def dense_search(
    conn: sqlite3.Connection,
    query_vec: list[float],
    *,
    limit: int = DEFAULT_TOP_M,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            c.id AS chunk_id,
            c.note_id AS note_id,
            c.ord AS ord,
            c.text AS text,
            c.embedding AS embedding,
            n.title AS title,
            n.summary AS summary,
            n.tags_json AS tags_json
        FROM chunks c
        JOIN notes n ON n.id = c.note_id
        WHERE c.embedding IS NOT NULL
        """
    ).fetchall()

    scored: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        vec = unpack_embedding(row["embedding"])
        if vec is None:
            continue
        score = _cosine(query_vec, vec)
        tags = json.loads(row["tags_json"] or "[]")
        scored.append(
            (
                score,
                {
                    "chunk_id": int(row["chunk_id"]),
                    "note_id": int(row["note_id"]),
                    "ord": int(row["ord"]),
                    "text": str(row["text"]),
                    "title": str(row["title"]),
                    "summary": str(row["summary"] or ""),
                    "tags": tags,
                    "dense_score": score,
                },
            )
        )
    scored.sort(key=lambda x: x[0], reverse=True)
    out: list[dict[str, Any]] = []
    for rank, (_score, item) in enumerate(scored[:limit], start=1):
        item["dense_rank"] = rank
        out.append(item)
    return out


def rrf_fuse(
    fts_hits: list[dict[str, Any]],
    dense_hits: list[dict[str, Any]],
    *,
    k: int = RRF_K,
) -> list[ChunkHit]:
    by_id: dict[int, ChunkHit] = {}

    for item in fts_hits:
        cid = int(item["chunk_id"])
        rank = int(item["fts_rank"])
        hit = by_id.get(cid)
        if hit is None:
            hit = ChunkHit(
                chunk_id=cid,
                note_id=int(item["note_id"]),
                ord=int(item["ord"]),
                text=str(item["text"]),
                title=str(item["title"]),
                summary=str(item["summary"]),
                tags=list(item.get("tags") or []),
            )
            by_id[cid] = hit
        hit.fts_rank = rank
        hit.rrf_score += 1.0 / (k + rank)

    for item in dense_hits:
        cid = int(item["chunk_id"])
        rank = int(item["dense_rank"])
        hit = by_id.get(cid)
        if hit is None:
            hit = ChunkHit(
                chunk_id=cid,
                note_id=int(item["note_id"]),
                ord=int(item["ord"]),
                text=str(item["text"]),
                title=str(item["title"]),
                summary=str(item["summary"]),
                tags=list(item.get("tags") or []),
            )
            by_id[cid] = hit
        hit.dense_rank = rank
        hit.dense_score = float(item.get("dense_score") or 0.0)
        hit.rrf_score += 1.0 / (k + rank)

    return sorted(by_id.values(), key=lambda h: h.rrf_score, reverse=True)


def retrieve(
    conn: sqlite3.Connection,
    question: str,
    *,
    expand_terms: list[str] | None = None,
    top_m: int = DEFAULT_TOP_M,
) -> RetrieveResult:
    t0 = time.perf_counter()
    terms = expand_terms or []
    fts_q = build_fts_query(terms, question)
    fts_hits = fts_search(conn, fts_q, limit=top_m)

    dense_hits: list[dict[str, Any]] = []
    mode = "fts-only"
    if is_available():
        try:
            qvec = embed_text(question)
            dense_hits = dense_search(conn, qvec, limit=top_m)
            if dense_hits:
                mode = "hybrid"
        except OllamaUnavailableError:
            mode = "fts-only"
    else:
        mode = "fts-only"

    if dense_hits and fts_hits:
        fused = rrf_fuse(fts_hits, dense_hits)
        mode = "hybrid"
    elif dense_hits:
        fused = rrf_fuse([], dense_hits)
        mode = "hybrid"
    else:
        fused = rrf_fuse(fts_hits, [])
        mode = "fts-only"

    latency_ms = (time.perf_counter() - t0) * 1000
    return RetrieveResult(
        hits=fused,
        mode=mode,
        expand_terms=terms,
        fts_count=len(fts_hits),
        dense_count=len(dense_hits),
        latency_ms=latency_ms,
    )


def notes_from_hits(hits: list[ChunkHit], *, limit: int = 10) -> list[dict[str, Any]]:
    """Deduplicate hits to note-level cards preserving RRF order."""
    seen: set[int] = set()
    notes: list[dict[str, Any]] = []
    for hit in hits:
        if hit.note_id in seen:
            continue
        seen.add(hit.note_id)
        notes.append(
            {
                "id": hit.note_id,
                "title": hit.title,
                "summary": hit.summary,
                "tags": hit.tags,
                "rrf_score": hit.rrf_score,
                "best_chunk_id": hit.chunk_id,
            }
        )
        if len(notes) >= limit:
            break
    return notes
