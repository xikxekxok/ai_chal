"""Persist notes/chunks, FTS index, embeddings, list/stats/clear/reindex."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from chunking import chunk_text
from db import DB_PATH, get_connection
from embeddings import OllamaUnavailableError, embed_text, pack_embedding


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _tags_str(tags: list[str]) -> str:
    return " ".join(t.strip() for t in tags if t.strip())


def _aliases_str(aliases: list[str]) -> str:
    return " ".join(a.strip() for a in aliases if a.strip())


@dataclass
class NoteRecord:
    id: int
    title: str
    body: str
    summary: str
    tags: list[str]
    aliases: list[str]
    created_at: str
    updated_at: str


def _row_to_note(row: sqlite3.Row) -> NoteRecord:
    return NoteRecord(
        id=int(row["id"]),
        title=str(row["title"]),
        body=str(row["body"]),
        summary=str(row["summary"] or ""),
        tags=json.loads(row["tags_json"] or "[]"),
        aliases=json.loads(row["aliases_json"] or "[]"),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def clear_db(conn: sqlite3.Connection | None = None) -> None:
    own = conn is None
    if own:
        conn = get_connection()
    assert conn is not None
    conn.execute("DELETE FROM chunks_fts")
    conn.execute("DELETE FROM chunks")
    conn.execute("DELETE FROM notes")
    conn.commit()
    if own:
        conn.close()


def insert_note(
    *,
    title: str,
    body: str,
    summary: str = "",
    tags: list[str] | None = None,
    aliases: list[str] | None = None,
    embed: bool = True,
    conn: sqlite3.Connection | None = None,
) -> tuple[NoteRecord, int, int]:
    """Insert note + chunks (+ optional embeddings). Returns (note, n_chunks, n_embedded)."""
    own = conn is None
    if own:
        conn = get_connection()
    assert conn is not None

    tags = tags or []
    aliases = aliases or []
    now = _now_iso()
    chunks = chunk_text(body)
    if not chunks:
        chunks = [body.strip() or title]

    cur = conn.execute(
        """
        INSERT INTO notes (title, body, summary, tags_json, aliases_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            title,
            body,
            summary,
            json.dumps(tags, ensure_ascii=False),
            json.dumps(aliases, ensure_ascii=False),
            now,
            now,
        ),
    )
    note_id = int(cur.lastrowid)
    tags_s = _tags_str(tags)
    aliases_s = _aliases_str(aliases)
    n_embedded = 0

    for ord_, text in enumerate(chunks):
        emb_blob: bytes | None = None
        dims: int | None = None
        if embed:
            try:
                vec = embed_text(text)
                emb_blob = pack_embedding(vec)
                dims = len(vec)
                n_embedded += 1
                print(
                    f"[embed] chunk {ord_ + 1}/{len(chunks)} dims={dims}",
                    flush=True,
                )
            except OllamaUnavailableError as exc:
                print(f"[embed] skip: {exc}", flush=True)
                embed = False  # don't spam remaining chunks

        cur = conn.execute(
            """
            INSERT INTO chunks (note_id, ord, text, embedding, dims)
            VALUES (?, ?, ?, ?, ?)
            """,
            (note_id, ord_, text, emb_blob, dims),
        )
        chunk_id = int(cur.lastrowid)
        conn.execute(
            """
            INSERT INTO chunks_fts (rowid, text, title, tags, aliases, summary)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (chunk_id, text, title, tags_s, aliases_s, summary),
        )

    conn.commit()
    note = get_note(note_id, conn=conn)
    assert note is not None
    if own:
        conn.close()
    return note, len(chunks), n_embedded


def get_note(note_id: int, *, conn: sqlite3.Connection | None = None) -> NoteRecord | None:
    own = conn is None
    if own:
        conn = get_connection()
    assert conn is not None
    row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    if own:
        conn.close()
    return _row_to_note(row) if row else None


def list_notes(
    *,
    limit: int = 20,
    conn: sqlite3.Connection | None = None,
) -> list[NoteRecord]:
    own = conn is None
    if own:
        conn = get_connection()
    assert conn is not None
    rows = conn.execute(
        "SELECT * FROM notes ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    if own:
        conn.close()
    return [_row_to_note(r) for r in rows]


def stats(*, conn: sqlite3.Connection | None = None, db_path: Path | None = None) -> dict[str, Any]:
    path = db_path or DB_PATH
    own = conn is None
    if own:
        conn = get_connection(path)
    assert conn is not None

    n_notes = int(conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0])
    n_chunks = int(conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
    n_emb = int(
        conn.execute("SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL").fetchone()[0]
    )
    size_bytes = path.stat().st_size if path.exists() else 0
    if own:
        conn.close()
    return {
        "notes": n_notes,
        "chunks": n_chunks,
        "with_embedding": n_emb,
        "without_embedding": n_chunks - n_emb,
        "db_path": str(path),
        "db_bytes": size_bytes,
    }


def reindex_embeddings(*, conn: sqlite3.Connection | None = None) -> tuple[int, int]:
    """Recompute embeddings for all chunks. Returns (ok, failed)."""
    own = conn is None
    if own:
        conn = get_connection()
    assert conn is not None

    rows = conn.execute("SELECT id, text FROM chunks ORDER BY id").fetchall()
    ok = 0
    failed = 0
    total = len(rows)
    for i, row in enumerate(rows, start=1):
        chunk_id = int(row["id"])
        text = str(row["text"])
        try:
            vec = embed_text(text)
            blob = pack_embedding(vec)
            conn.execute(
                "UPDATE chunks SET embedding = ?, dims = ? WHERE id = ?",
                (blob, len(vec), chunk_id),
            )
            ok += 1
            print(f"[embed] reindex {i}/{total} chunk_id={chunk_id} dims={len(vec)}", flush=True)
        except OllamaUnavailableError as exc:
            failed += 1
            print(f"[embed] fail chunk_id={chunk_id}: {exc}", flush=True)
            if failed == 1 and ok == 0:
                # first failure with nothing done — abort early
                break
    conn.commit()
    if own:
        conn.close()
    return ok, failed
