#!/usr/bin/env python3
"""RAG over opossum index: RU question → EN retrieve → LLM → RU answer."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from console_out import clear_screen, pause, print_demo_line, print_index_line, print_section
from embeddings import check_ollama
from paths import INDEX_PATH
from questions import DEMO_QUESTIONS, DemoQuestion
from rag import generate_with_rag, generate_without_rag
from retrieve import retrieve
from store import load_index
from translate import translate_to_en


def format_size_mb(path: Any) -> str:
    size = path.stat().st_size
    return f"{size / (1024 * 1024):.1f} MB"


def cmd_show_index() -> None:
    if not INDEX_PATH.is_file():
        print_index_line("[index] no index yet")
        print_index_line(f"[index] path: {INDEX_PATH}")
        print_index_line(
            "[index] build: python weeks/week-05/day-01/init_data.py → "
            "python weeks/week-05/day-01/main.py --index"
        )
        return

    data = load_index()
    stats = data.get("stats", {})
    chunking = data.get("chunking", {})
    embedding = data.get("embedding", {})
    print_index_line(f"[index] path: {INDEX_PATH} ({format_size_mb(INDEX_PATH)})")
    print_index_line(
        "[index] stats: "
        f"books={stats.get('books', 0)} "
        f"chunks={stats.get('chunks', 0)} "
        f"avg_chars={stats.get('avg_chars', 0)} "
        f"total_chars={stats.get('total_chars', 0)}"
    )
    print_index_line(
        "[index] chunking: "
        f"strategy={chunking.get('strategy')} "
        f"chunk_chars={chunking.get('chunk_chars')} "
        f"overlap_chars={chunking.get('overlap_chars')}"
    )
    print_index_line(
        "[index] embedding: "
        f"provider={embedding.get('provider')} "
        f"model={embedding.get('model')} "
        f"dim={embedding.get('dim')}"
    )
    print_index_line(f"[index] created_at: {data.get('created_at', 'n/a')}")


def _format_expect(item: DemoQuestion) -> str:
    lines = [item.expect_ru, "", "источники:"]
    for source_id, title in zip(item.source_ids, item.source_titles, strict=True):
        lines.append(f"  {source_id} — {title}")
    return "\n".join(lines)


def _run_flow(
    question_ru: str,
    chunks: list[dict[str, Any]],
    *,
    expect: DemoQuestion | None = None,
    with_rag: bool = True,
    without_rag: bool = False,
) -> None:
    print_section("question", question_ru)

    if expect is not None:
        print_section("expect", _format_expect(expect), layout="block")

    question_en = translate_to_en(question_ru)
    hits = retrieve(question_en, chunks)

    print_section("question-en", question_en)

    if with_rag:
        print_section("answer-rag", generate_with_rag(question_en, hits))

    if without_rag:
        print_section("answer-no-rag", generate_without_rag(question_ru))


def cmd_ask(question: str, *, use_rag: bool) -> None:
    data = load_index()
    check_ollama()
    if use_rag:
        _run_flow(question, data["chunks"], with_rag=True, without_rag=False)
    else:
        print_section("question", question)
        print_section("answer-no-rag", generate_without_rag(question))


def cmd_compare(question: str) -> None:
    data = load_index()
    check_ollama()
    _run_flow(question, data["chunks"], with_rag=True, without_rag=True)


def cmd_demo(*, no_pause: bool) -> None:
    data = load_index()
    check_ollama()
    chunks = data["chunks"]
    total = len(DEMO_QUESTIONS)

    print_demo_line("[demo] RAG по индексу опossумов: question → expect → question-en → answers")
    print_demo_line(f"[demo] вопросов: {total}")
    print()
    pause("Enter — начать демо", no_pause=no_pause)

    for index, item in enumerate(DEMO_QUESTIONS, start=1):
        clear_screen()
        print_demo_line(f"[demo] вопрос {index}/{total}")
        print()
        _run_flow(
            item.question_ru,
            chunks,
            expect=item,
            with_rag=True,
            without_rag=True,
        )
        if index < total:
            pause("Enter — следующий вопрос", no_pause=no_pause)


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG over opossum index (RU ↔ EN).")
    parser.add_argument("--ask", metavar="QUESTION", help="Ask one question (Russian).")
    parser.add_argument("--no-rag", action="store_true", help="Answer without retrieval.")
    parser.add_argument(
        "--compare",
        metavar="QUESTION",
        help="Compare RAG vs no-RAG on one question.",
    )
    parser.add_argument("--demo", action="store_true", help="Run 10 demo questions.")
    parser.add_argument(
        "--no-pause",
        action="store_true",
        help="Demo without pause between questions.",
    )
    parser.add_argument(
        "--show-index",
        action="store_true",
        help="Show index stats (no Ollama/LLM).",
    )
    args = parser.parse_args()

    if args.show_index:
        cmd_show_index()
        return

    if args.demo:
        cmd_demo(no_pause=args.no_pause)
        return

    if args.compare:
        cmd_compare(args.compare)
        return

    if args.ask:
        cmd_ask(args.ask, use_rag=not args.no_rag)
        return

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
