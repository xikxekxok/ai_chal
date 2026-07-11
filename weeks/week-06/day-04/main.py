#!/usr/bin/env python3
"""Оптимизированный локальный RAG (cite + simple) на qwen3:4b. Перевод — облако."""

from __future__ import annotations

import argparse
import sys
from typing import Any, Literal

from console_out import (
    clear_screen,
    pause,
    print_demo_line,
    print_fallback_banner,
    print_index_line,
    print_section,
    print_stage_header,
    print_tagged,
)
from embeddings import check_ollama as check_ollama_embed
from llm import check_ollama
from paths import INDEX_PATH
from pipeline_cite import PipelineResult, run_cite_pipeline
from profiles import RAGProfile, load_profile
from questions import DEMO_QUESTIONS, DemoQuestion
from rag_cite import RagResponse, format_chunks_used, format_rag_summary
from rag_simple import generate_simple_rag
from retrieve import retrieve
from store import load_index
from translate import translate_to_en

Mode = Literal["both", "cite", "simple"]


def format_size_mb(path: Any) -> str:
    size = path.stat().st_size
    return f"{size / (1024 * 1024):.1f} MB"


def _format_expect(item: DemoQuestion) -> str:
    lines = [item.expect_ru, "", "источники:"]
    for source_id, title in zip(item.source_ids, item.source_titles, strict=True):
        lines.append(f"  {source_id} — {title}")
    return "\n".join(lines)


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


def _print_rag_block(stage: str, resp: RagResponse) -> None:
    print_tagged(f"rag-{stage}", format_rag_summary(resp))
    print_section(f"chunks-{stage}", format_chunks_used(resp.hits), layout="block")


def _print_cite_response(result: PipelineResult) -> None:
    if result.response is not None:
        print_stage_header("rerank", "Ответ по чанкам после rerank")
        _print_rag_block("rerank", result.response)

    if result.response_wide is not None:
        print_fallback_banner(chunk_count=len(result.retrieve_hits))
        print_stage_header("wide", "Повторный ответ: cosine-чанки без rerank")
        _print_rag_block("wide", result.response_wide)


def _run_cite(
    question_ru: str,
    question_en: str,
    chunks: list[dict[str, Any]],
    profile: RAGProfile,
) -> PipelineResult:
    print_stage_header("cite", "Режим 5.4: rerank + цитаты (локальная LLM)")
    return run_cite_pipeline(question_ru, question_en, chunks, profile)


def _run_simple(
    question_en: str,
    chunks: list[dict[str, Any]],
    profile: RAGProfile,
) -> None:
    print_stage_header(
        "simple",
        f"Режим 5.2: cosine top-{profile.simple_top_k}, простой RAG (локальная LLM)",
    )
    hits = retrieve(question_en, chunks, top_k=profile.simple_top_k)
    print_tagged("retrieve", f"top-{len(hits)} cosine")
    generate_simple_rag(question_en, hits, profile)


def _run_question(
    question_ru: str,
    chunks: list[dict[str, Any]],
    profile: RAGProfile,
    *,
    expect: DemoQuestion | None = None,
    mode: Mode,
    question_en: str | None = None,
) -> None:
    print_section("question", question_ru)
    if expect is not None:
        print_section("expect", _format_expect(expect), layout="block")

    if question_en is None:
        question_en = translate_to_en(question_ru)
    print_section("question-en", question_en)

    if mode in ("both", "cite"):
        result = _run_cite(question_ru, question_en, chunks, profile)
        _print_cite_response(result)

    if mode in ("both", "simple"):
        if mode == "both":
            print()
        _run_simple(question_en, chunks, profile)


def cmd_ask(question: str, *, profile: RAGProfile, mode: Mode) -> None:
    data = load_index()
    check_ollama_embed()
    _run_question(question, data["chunks"], profile, mode=mode)


def cmd_demo(*, no_pause: bool, profile: RAGProfile) -> None:
    data = load_index()
    check_ollama_embed()
    chunks = data["chunks"]
    total = len(DEMO_QUESTIONS)

    print_demo_line("оптимизированный локальный RAG: cite (5.4) + simple (5.2); translate — cloud")
    print_demo_line(profile.summary())
    print_demo_line(f"[demo] вопросов: {total}")
    print()
    pause("Enter — начать демо", no_pause=no_pause)

    for index, item in enumerate(DEMO_QUESTIONS, start=1):
        clear_screen()
        print_demo_line(f"вопрос {index}/{total}")
        print()
        question_en = translate_to_en(item.question_ru)
        _run_question(
            item.question_ru,
            chunks,
            profile,
            expect=item,
            mode="both",
            question_en=question_en,
        )
        if index < total:
            pause("Enter — следующий вопрос", no_pause=no_pause)


def main() -> None:
    profile = load_profile()
    parser = argparse.ArgumentParser(
        description="Optimized local RAG on qwen3:4b (cite + simple)."
    )
    parser.add_argument("--ask", metavar="QUESTION", help="Ask one question (Russian).")
    parser.add_argument("--demo", action="store_true", help="Run 2 demo questions (both modes).")
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
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check Ollama server and models.",
    )
    parser.add_argument(
        "--mode",
        choices=("both", "cite", "simple"),
        default="both",
        help="RAG mode for --ask (default: both).",
    )
    args = parser.parse_args()

    if args.check:
        check_ollama()
        return

    if args.show_index:
        cmd_show_index()
        return

    if args.demo:
        cmd_demo(no_pause=args.no_pause, profile=profile)
        return

    if args.ask:
        cmd_ask(args.ask, profile=profile, mode=args.mode)
        return

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
