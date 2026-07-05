#!/usr/bin/env python3
"""RAG with rerank, mandatory sources and citations."""

from __future__ import annotations

import argparse
import sys
from typing import Any

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
from embeddings import check_ollama
from paths import INDEX_PATH
from pipeline import PipelineConfig, PipelineResult, run_pipeline
from questions import DEMO_QUESTIONS, DemoQuestion
from rag import RagResponse, format_citations, format_rag_summary, format_sources
from store import load_index
from verify import VerifyTotals, format_verify, print_verify_total, verify_response


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
    print_tagged(f"rag-{stage}", format_rag_summary(stage, resp))
    flag = "да" if resp.context_sufficient else "нет"
    context_lines = [f"context_sufficient={flag}"]
    if resp.clarification_hint:
        context_lines.append(f"clarification_hint: {resp.clarification_hint}")
    print_section(f"context-{stage}", "\n".join(context_lines), layout="block")
    print_section(f"rag-{stage}", resp.answer)
    print_section(f"sources-{stage}", format_sources(resp.sources), layout="block")
    print_section(f"citations-{stage}", format_citations(resp.citations), layout="block")


def _print_response(result: PipelineResult) -> None:
    if result.response is not None:
        print_stage_header("rerank", "Ответ по чанкам после rerank")
        _print_rag_block("rerank", result.response)

    if result.response_wide is not None:
        print_fallback_banner(chunk_count=len(result.retrieve_hits))
        print_stage_header("wide", "Повторный ответ: cosine-чанки без rerank")
        _print_rag_block("wide", result.response_wide)


def _verify_rerank(
    question_ru: str,
    result: PipelineResult,
    totals: VerifyTotals,
) -> None:
    if result.response is None:
        return
    v = verify_response(question_ru, result.response, result.rag_hits)
    print_section("verify", format_verify(v), layout="block")
    totals.total += 1
    if v.context_sufficient:
        totals.context_ok += 1
    if v.has_sources:
        totals.sources_ok += 1
    if v.has_citations:
        totals.citations_ok += 1
    if v.grounded:
        totals.grounded_ok += 1


def _verify_wide(
    question_ru: str,
    result: PipelineResult,
    totals: VerifyTotals,
) -> None:
    if result.response_wide is None:
        return
    vw = verify_response(question_ru, result.response_wide, result.retrieve_hits)
    print_section("verify-wide", format_verify(vw), layout="block")
    totals.wide_total += 1
    if result.response_wide.context_sufficient:
        totals.wide_sufficient += 1


def _print_and_verify(
    question_ru: str,
    result: PipelineResult,
    totals: VerifyTotals,
) -> None:
    if result.response is not None:
        print_stage_header("rerank", "Ответ по чанкам после rerank")
        _print_rag_block("rerank", result.response)
        _verify_rerank(question_ru, result, totals)

    if result.response_wide is not None:
        print_fallback_banner(chunk_count=len(result.retrieve_hits))
        print_stage_header("wide", "Повторный ответ: cosine-чанки без rerank")
        _print_rag_block("wide", result.response_wide)
        _verify_wide(question_ru, result, totals)


def cmd_ask(question: str, args: argparse.Namespace) -> None:
    data = load_index()
    check_ollama()
    cfg = _build_config(args)
    print_section("question", question)
    result = run_pipeline(question, data["chunks"], cfg)
    _print_response(result)


def cmd_demo(*, no_pause: bool, args: argparse.Namespace) -> None:
    data = load_index()
    check_ollama()
    chunks = data["chunks"]
    cfg = _build_config(args)
    total = len(DEMO_QUESTIONS)
    totals = VerifyTotals()

    print_demo_line("[demo] rerank RAG · sources + citations · 10 вопросов из day-02")
    print_demo_line(f"[demo] вопросов: {total}")
    print()
    pause("Enter — начать демо", no_pause=no_pause)

    for index, item in enumerate(DEMO_QUESTIONS, start=1):
        clear_screen()
        print_demo_line(f"[demo] вопрос {index}/{total}")
        print()
        print_section("question", item.question_ru)
        print_section("expect", _format_expect(item), layout="block")

        result = run_pipeline(item.question_ru, chunks, cfg)
        _print_and_verify(item.question_ru, result, totals)

        if index < total:
            pause("Enter — следующий вопрос", no_pause=no_pause)

    clear_screen()
    print_demo_line("[demo] итог проверки")
    print()
    print_verify_total(totals)


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG with rerank, sources and citations.")
    parser.add_argument("--ask", metavar="QUESTION", help="Ask one question (Russian).")
    parser.add_argument("--demo", action="store_true", help="Run 10 demo questions with verify.")
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
    parser.add_argument("--retrieve-k", type=int, default=20, help="Top-K before rerank.")
    parser.add_argument("--rag-k", type=int, default=4, help="Top-K after rerank filter.")
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.15,
        help="CrossEncoder score threshold (default 0.15).",
    )
    args = parser.parse_args()

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
