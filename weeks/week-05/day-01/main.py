#!/usr/bin/env python3
"""Build opossum document index: chunking → Ollama embeddings → JSON."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from chunking import chunk_text
from embeddings import check_ollama, embed_text
from paths import INDEX_PATH, RAW_DIR
from progress import EmbedProgress, StageTimer
from sources import BOOKS
from store import build_index, format_size_mb, load_index, save_index


def expected_filenames() -> str:
    return ", ".join(book.filename for book in BOOKS)


def load_raw_books() -> list[tuple[Any, str]]:
    if not RAW_DIR.is_dir() or not any(RAW_DIR.iterdir()):
        print(
            "[error] data/raw пуст — сначала: python weeks/week-05/day-01/init_data.py",
            file=sys.stderr,
        )
        print(f"[error] ожидаются: {expected_filenames()}", file=sys.stderr)
        raise SystemExit(1)

    loaded: list[tuple[Any, str]] = []
    missing: list[str] = []

    for book in BOOKS:
        path = RAW_DIR / book.filename
        if not path.is_file():
            missing.append(book.filename)
            continue
        loaded.append((book, path.read_text(encoding="utf-8")))

    if missing:
        print(
            f"[error] missing raw files ({len(missing)}/{len(BOOKS)}): {', '.join(missing)}",
            file=sys.stderr,
        )
        print(
            "[error] сначала: python weeks/week-05/day-01/init_data.py",
            file=sys.stderr,
        )
        raise SystemExit(1)

    return loaded


def cmd_index() -> None:
    timer = StageTimer()
    print("[index] load raw corpus")

    books = load_raw_books()
    total_chars = sum(len(text) for _, text in books)
    print(f"[index] load: {len(books)}/{len(BOOKS)} books, {total_chars // 1024} KB total")

    print("[index] chunk overlap")
    all_drafts: list[Any] = []
    for book_index, (book, text) in enumerate(books, start=1):
        drafts = chunk_text(text, book)
        all_drafts.extend(drafts)
        print(f"[index] chunk: book {book_index}/{len(BOOKS)} → {len(drafts)} chunks")
    print(f"[index] chunk: total {len(all_drafts)} chunks")

    check_ollama()
    print("[index] embed via Ollama")
    progress = EmbedProgress(len(all_drafts))
    embedded: list[dict[str, Any]] = []

    for draft in all_drafts:
        vector = embed_text(draft.text)
        embedded.append(
            {
                "text": draft.text,
                "embedding": vector,
                "meta": draft.meta,
            }
        )
        progress.tick()
        progress.maybe_print()

    progress.maybe_print(force=True)

    print("[index] save index")
    index_data = build_index(embedded)
    save_index(index_data)
    print(f"[index] save: {INDEX_PATH} ({format_size_mb(INDEX_PATH)})")

    sample = embedded[0]["meta"] if embedded else {}
    print(
        f"[index] done: {index_data['stats']['chunks']} chunks, "
        f"{index_data['stats']['books']} books, wall {timer.elapsed_str()}"
    )
    if sample:
        print(
            "[index] sample: "
            f"chunk_id={sample.get('chunk_id')} "
            f"section={sample.get('section')!r} "
            f"char_count={sample.get('char_count')}"
        )


def cmd_show_index() -> None:
    data = load_index()
    if data is None:
        print("[index] no index yet")
        print(f"[index] path: {INDEX_PATH}")
        return

    stats = data.get("stats", {})
    chunking = data.get("chunking", {})
    embedding = data.get("embedding", {})
    print(f"[index] path: {INDEX_PATH} ({format_size_mb(INDEX_PATH)})")
    print(
        "[index] stats: "
        f"books={stats.get('books', 0)} "
        f"chunks={stats.get('chunks', 0)} "
        f"avg_chars={stats.get('avg_chars', 0)} "
        f"total_chars={stats.get('total_chars', 0)}"
    )
    print(
        "[index] chunking: "
        f"strategy={chunking.get('strategy')} "
        f"chunk_chars={chunking.get('chunk_chars')} "
        f"overlap_chars={chunking.get('overlap_chars')}"
    )
    print(
        "[index] embedding: "
        f"provider={embedding.get('provider')} "
        f"model={embedding.get('model')} "
        f"dim={embedding.get('dim')}"
    )
    print(f"[index] created_at: {data.get('created_at', 'n/a')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Index opossum corpus: chunk → embed → JSON.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--index", action="store_true", help="Build index from raw texts.")
    group.add_argument("--show-index", action="store_true", help="Show index stats (no Ollama).")
    args = parser.parse_args()

    if args.index:
        cmd_index()
    elif args.show_index:
        cmd_show_index()


if __name__ == "__main__":
    main()
