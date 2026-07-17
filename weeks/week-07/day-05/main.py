#!/usr/bin/env python3
"""Day 35 — CLI second brain (SQLite FTS5 + Ollama embeddings + Dockhost)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# allow `python weeks/week-07/day-05/main.py` from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))

from brain import (  # noqa: E402
    DEMO_ASK,
    DEMO_NOTE_1,
    DEMO_NOTE_2,
    ask,
    save_text,
    search_text,
)
from db import get_connection  # noqa: E402
from llm import UsageTracker, load_llm_config, try_load_llm_config  # noqa: E402
from retrieve import notes_from_hits  # noqa: E402
from store import clear_db, get_note, list_notes, reindex_embeddings, stats  # noqa: E402


def _print_stats() -> None:
    s = stats()
    print(
        f"[stats] notes={s['notes']} chunks={s['chunks']} "
        f"embedded={s['with_embedding']} missing_emb={s['without_embedding']} "
        f"db={s['db_bytes']}B ({s['db_path']})",
        flush=True,
    )


def _print_notes_list(limit: int) -> None:
    notes = list_notes(limit=limit)
    print(f"[notes] list limit={limit} count={len(notes)}", flush=True)
    for n in notes:
        tags = ",".join(n.tags) if n.tags else "—"
        print(f"  #{n.id} {n.title}  [{tags}]  {n.created_at}", flush=True)


def _print_note(note_id: int) -> None:
    note = get_note(note_id)
    if note is None:
        print(f"[error] заметка id={note_id} не найдена", file=sys.stderr)
        sys.exit(1)
    print(f"[notes] id={note.id} title={note.title!r}", flush=True)
    print(f"  tags: {note.tags}", flush=True)
    print(f"  aliases: {note.aliases}", flush=True)
    print(f"  summary: {note.summary or '—'}", flush=True)
    print(f"  created: {note.created_at}  updated: {note.updated_at}", flush=True)
    print("--- body ---", flush=True)
    print(note.body, flush=True)


def _print_retrieve_hits(result, *, limit: int = 8) -> None:
    cards = notes_from_hits(result.hits, limit=limit)
    print(f"[notes] top={len(cards)} (from retrieve)", flush=True)
    for c in cards:
        tags = ",".join(c["tags"]) if c["tags"] else "—"
        print(
            f"  #{c['id']} {c['title']}  rrf={c['rrf_score']:.4f}  [{tags}]",
            flush=True,
        )


def cmd_demo() -> int:
    print(
        "[demo] Second brain: clear → 2 save → search → ask "
        "(FTS + dense RRF, Dockhost enrich/answer)",
        flush=True,
    )
    clear_db()
    print("[demo] DB cleared", flush=True)
    tracker = UsageTracker()
    cfg = load_llm_config()

    print("[demo] save note 1 (API rate limiting)…", flush=True)
    r1 = save_text(DEMO_NOTE_1, config=cfg, tracker=tracker)
    _print_note(r1.note.id)
    print("[demo] save note 2 (Redis cache)…", flush=True)
    r2 = save_text(DEMO_NOTE_2, config=cfg, tracker=tracker)
    _print_note(r2.note.id)

    print("[demo] search…", flush=True)
    search_q = "throttle API requests Retry-After"
    result = search_text(search_q, config=cfg, tracker=tracker)
    _print_retrieve_hits(result)

    print(f"[demo] ask: {DEMO_ASK}", flush=True)
    ask_result = ask(DEMO_ASK, config=cfg, tracker=tracker)
    print("[ask] --- answer ---", flush=True)
    print(ask_result.answer, flush=True)
    _print_retrieve_hits(ask_result.retrieve)
    print(tracker.summary_line(), flush=True)
    _print_stats()
    print("[demo] done", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Day 35 — personal second brain (SQLite+FTS5+Ollama+Dockhost)",
    )
    p.add_argument("--save", metavar="TEXT", help="добавить заметку")
    p.add_argument("--ask", metavar="QUESTION", help="вопрос к базе")
    p.add_argument("--search", metavar="QUERY", help="только retrieve (без LLM-ответа)")
    p.add_argument("--list", action="store_true", help="последние заметки")
    p.add_argument("--limit", type=int, default=20, help="лимит для --list (default 20)")
    p.add_argument("--show", type=int, metavar="ID", help="показать заметку по id")
    p.add_argument("--stats", action="store_true", help="статистика БД")
    p.add_argument(
        "--reindex-embeddings",
        action="store_true",
        help="пересчитать Ollama-эмбеддинги всех чанков",
    )
    p.add_argument("--demo", action="store_true", help="полный демо-сценарий для видео")
    p.add_argument("--clear", action="store_true", help="очистить brain.db")
    p.add_argument(
        "--no-enrich",
        action="store_true",
        help="save без LLM-обогащения (сырой текст)",
    )
    p.add_argument(
        "--no-expand",
        action="store_true",
        help="search без LLM query expand",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # ensure schema even for empty ops
    get_connection().close()

    primary = [
        name
        for name, flag in (
            ("--save", args.save is not None),
            ("--ask", args.ask is not None),
            ("--search", args.search is not None),
            ("--list", args.list),
            ("--show", args.show is not None),
            ("--stats", args.stats),
            ("--reindex-embeddings", args.reindex_embeddings),
            ("--demo", args.demo),
            ("--clear", args.clear),
        )
        if flag
    ]
    if not primary:
        build_parser().print_help()
        return 0
    if len(primary) > 1:
        print(
            f"[error] укажите одну команду, получено: {', '.join(primary)}",
            file=sys.stderr,
        )
        return 2

    if args.clear:
        clear_db()
        print("[stats] cleared brain.db", flush=True)
        _print_stats()
        return 0

    if args.demo:
        return cmd_demo()

    if args.stats:
        _print_stats()
        return 0

    if args.list:
        _print_notes_list(args.limit)
        return 0

    if args.show is not None:
        _print_note(args.show)
        return 0

    if args.reindex_embeddings:
        ok, failed = reindex_embeddings()
        print(f"[embed] reindex done ok={ok} failed={failed}", flush=True)
        _print_stats()
        return 0 if failed == 0 or ok > 0 else 1

    if args.save is not None:
        tracker = UsageTracker()
        cfg = None if args.no_enrich else try_load_llm_config()
        if not args.no_enrich and cfg is None:
            print(
                "[save] нет DOCKHOST_AI_KEY → save без enrich",
                flush=True,
            )
        save_text(args.save, no_enrich=args.no_enrich or cfg is None, tracker=tracker)
        if tracker.calls:
            print(tracker.summary_line(), flush=True)
        return 0

    if args.search is not None:
        tracker = UsageTracker()
        cfg = try_load_llm_config() if not args.no_expand else None
        result = search_text(
            args.search,
            expand=not args.no_expand,
            config=cfg,
            tracker=tracker,
        )
        _print_retrieve_hits(result, limit=10)
        # also show top chunks briefly
        for hit in result.hits[:5]:
            preview = " ".join(hit.text.split())[:100]
            print(
                f"  chunk#{hit.chunk_id} note#{hit.note_id} rrf={hit.rrf_score:.4f} | {preview}",
                flush=True,
            )
        if tracker.calls:
            print(tracker.summary_line(), flush=True)
        return 0

    if args.ask is not None:
        tracker = UsageTracker()
        cfg = load_llm_config()
        result = ask(args.ask, config=cfg, tracker=tracker)
        print("[ask] --- answer ---", flush=True)
        print(result.answer, flush=True)
        _print_retrieve_hits(result.retrieve)
        print(tracker.summary_line(), flush=True)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
