#!/usr/bin/env python3
"""Локальный RAG: cite (5.4 rerank) + simple (5.2 top-10). Перевод — облако."""

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
from llm import check_ollama, load_ollama_config
from paths import INDEX_PATH
from pipeline_cite import PipelineConfig, PipelineResult, run_cite_pipeline
from questions import DEMO_QUESTIONS, DemoQuestion
from rag_cite import RagResponse, format_citations, format_rag_summary, format_sources
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


def _build_config(args: argparse.Namespace) -> PipelineConfig:
    return PipelineConfig(
        retrieve_k=args.retrieve_k,
        rag_k=args.rag_k,
        min_score=args.min_score,
    )


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
    flag = "да" if resp.context_sufficient else "нет"
    context_lines = [f"context_sufficient={flag}"]
    if resp.clarification_hint:
        context_lines.append(f"clarification_hint: {resp.clarification_hint}")
    print_section(f"context-{stage}", "\n".join(context_lines), layout="block")
    print_section(f"rag-{stage}", resp.answer)
    print_section(f"sources-{stage}", format_sources(resp.sources), layout="block")
    print_section(f"citations-{stage}", format_citations(resp.citations), layout="block")


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
    config: PipelineConfig,
) -> PipelineResult:
    print_stage_header("cite", "Режим 5.4: rerank + цитаты (локальная LLM)")
    return run_cite_pipeline(question_ru, question_en, chunks, config)


def _run_simple(
    question_en: str,
    chunks: list[dict[str, Any]],
    *,
    top_k: int,
) -> None:
    print_stage_header("simple", "Режим 5.2: cosine top-10, простой RAG (локальная LLM)")
    hits = retrieve(question_en, chunks, top_k=top_k)
    print_tagged("retrieve", f"top-{len(hits)} cosine")
    answer, _latency = generate_simple_rag(question_en, hits)
    print_section("answer-rag", answer)


def _run_question(
    question_ru: str,
    chunks: list[dict[str, Any]],
    *,
    expect: DemoQuestion | None = None,
    config: PipelineConfig,
    top_k: int,
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
        result = _run_cite(question_ru, question_en, chunks, config)
        _print_cite_response(result)

    if mode in ("both", "simple"):
        if mode == "both":
            print()
        _run_simple(question_en, chunks, top_k=top_k)


def cmd_ask(question: str, args: argparse.Namespace) -> None:
    data = load_index()
    check_ollama_embed()
    cfg = _build_config(args)
    _run_question(
        question,
        data["chunks"],
        config=cfg,
        top_k=args.top_k,
        mode=args.mode,
    )


def cmd_demo(*, no_pause: bool, args: argparse.Namespace) -> None:
    data = load_index()
    check_ollama_embed()
    chunks = data["chunks"]
    cfg = _build_config(args)
    total = len(DEMO_QUESTIONS)
    cfg_local = load_ollama_config()

    print_demo_line(
        "[demo] локальный RAG: cite (5.4 rerank) + simple (5.2 top-10); translate — cloud"
    )
    print_demo_line(f"[demo] model: {cfg_local.model}")
    print_demo_line(f"[demo] вопросов: {total}")
    print()
    pause("Enter — начать демо", no_pause=no_pause)

    for index, item in enumerate(DEMO_QUESTIONS, start=1):
        clear_screen()
        print_demo_line(f"[demo] вопрос {index}/{total}")
        print()
        question_en = translate_to_en(item.question_ru)
        _run_question(
            item.question_ru,
            chunks,
            expect=item,
            config=cfg,
            top_k=args.top_k,
            mode="both",
            question_en=question_en,
        )
        if index < total:
            pause("Enter — следующий вопрос", no_pause=no_pause)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Local RAG: cite (rerank+citations) and simple (top-10)."
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
    parser.add_argument("--retrieve-k", type=int, default=20, help="Top-K before rerank.")
    parser.add_argument("--rag-k", type=int, default=4, help="Top-K after rerank filter.")
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.15,
        help="CrossEncoder score threshold (default 0.15).",
    )
    parser.add_argument("--top-k", type=int, default=10, help="Top-K for simple mode (default 10).")
    args = parser.parse_args()

    if args.check:
        check_ollama()
        return

    if args.show_index:
        cmd_show_index()
        return

    if args.demo:
        cmd_demo(no_pause=args.no_pause, args=args)
        return

    if args.ask:
        cmd_ask(args.ask, args)
        return

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
