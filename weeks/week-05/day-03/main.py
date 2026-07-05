#!/usr/bin/env python3
"""RAG with query rewrite, CrossEncoder rerank, and mode comparison."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from console_out import clear_screen, pause, print_demo_line, print_index_line, print_section
from embeddings import check_ollama
from evaluate import evaluate_answers, print_rating, print_total_rating
from paths import INDEX_PATH
from pipeline import ALL_MODES, MODE_LABELS, PipelineConfig, PipelineMode, run_pipeline
from questions import DEMO_QUESTIONS, DemoQuestion
from rewrite import rewrite_query
from store import load_index
from translate import translate_to_en


def _translate_and_rewrite(question_ru: str) -> tuple[str, str]:
    question_en = translate_to_en(question_ru)
    search_query_en = rewrite_query(question_en)
    return question_en, search_query_en


def format_size_mb(path: Any) -> str:
    size = path.stat().st_size
    return f"{size / (1024 * 1024):.1f} MB"


def _parse_mode(value: str) -> PipelineMode:
    try:
        return PipelineMode(value)
    except ValueError as exc:
        print(f"[error] неизвестный mode: {value!r} (bare|rewrite|rerank|both)", file=sys.stderr)
        raise SystemExit(1) from exc


def _build_config(args: argparse.Namespace, mode: PipelineMode) -> PipelineConfig:
    cfg = PipelineConfig.for_mode(mode).with_overrides(
        retrieve_k=args.retrieve_k,
        rag_k=args.rag_k,
        min_score=args.min_score,
        no_rewrite=args.no_rewrite,
        no_rerank=args.no_rerank,
    )
    if args.mode:
        cfg.mode = _parse_mode(args.mode)
    return cfg


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


def _run_mode(
    question_ru: str,
    chunks: list[dict[str, Any]],
    mode: PipelineMode,
    args: argparse.Namespace,
    *,
    question_en: str | None = None,
    search_query_en: str | None = None,
    show_answer: bool = True,
) -> str | None:
    print_section("mode", MODE_LABELS[mode], layout="block")
    cfg = PipelineConfig.for_mode(mode).with_overrides(
        retrieve_k=args.retrieve_k,
        rag_k=args.rag_k,
        min_score=args.min_score,
    )
    result = run_pipeline(
        question_ru,
        chunks,
        cfg,
        generate_answer=show_answer,
        question_en=question_en,
        search_query_en=search_query_en,
    )
    if show_answer and result.answer:
        print_section("rag", result.answer)
    return result.answer if show_answer else None


def cmd_ask(question: str, args: argparse.Namespace) -> None:
    data = load_index()
    check_ollama()
    mode = _parse_mode(args.mode) if args.mode else PipelineMode.BOTH
    cfg = _build_config(args, mode)
    print_section("question", question)
    question_en = translate_to_en(question)
    search_query_en: str | None = None
    if cfg.use_rewrite:
        search_query_en = rewrite_query(question_en)
    result = run_pipeline(
        question,
        data["chunks"],
        cfg,
        question_en=question_en,
        search_query_en=search_query_en,
    )
    if result.answer:
        print_section("rag", result.answer)


def cmd_retrieve(question: str, args: argparse.Namespace) -> None:
    data = load_index()
    check_ollama()
    mode = _parse_mode(args.mode) if args.mode else PipelineMode.BOTH
    cfg = _build_config(args, mode)
    print_section("question", question)
    question_en = translate_to_en(question)
    search_query_en: str | None = None
    if cfg.use_rewrite:
        search_query_en = rewrite_query(question_en)
    run_pipeline(
        question,
        data["chunks"],
        cfg,
        generate_answer=False,
        question_en=question_en,
        search_query_en=search_query_en,
    )


def cmd_compare_modes(question: str, args: argparse.Namespace) -> None:
    data = load_index()
    check_ollama()
    chunks = data["chunks"]
    print_section("question", question)
    question_en, search_query_en = _translate_and_rewrite(question)
    for mode in ALL_MODES:
        _run_mode(
            question,
            chunks,
            mode,
            args,
            question_en=question_en,
            search_query_en=search_query_en,
        )


def cmd_demo(*, no_pause: bool, args: argparse.Namespace) -> None:
    data = load_index()
    check_ollama()
    chunks = data["chunks"]
    total = len(DEMO_QUESTIONS)

    print_demo_line("[demo] 4 режима × 10 вопросов из day-02")
    print_demo_line(f"[demo] вопросов: {total}")
    print()
    pause("Enter — начать демо", no_pause=no_pause)

    all_scores: dict[PipelineMode, list[float]] = {mode: [] for mode in ALL_MODES}
    for index, item in enumerate(DEMO_QUESTIONS, start=1):
        clear_screen()
        print_demo_line(f"[demo] вопрос {index}/{total}")
        print()
        print_section("question", item.question_ru)
        print_section("expect", _format_expect(item), layout="block")
        question_en, search_query_en = _translate_and_rewrite(item.question_ru)
        answers: dict[PipelineMode, str] = {}
        for mode in ALL_MODES:
            answer = _run_mode(
                item.question_ru,
                chunks,
                mode,
                args,
                question_en=question_en,
                search_query_en=search_query_en,
            )
            if answer:
                answers[mode] = answer
        if answers:
            scores = evaluate_answers(item.question_ru, item.expect_ru, answers)
            print_rating(scores)
            for mode, score in scores.items():
                all_scores[mode].append(score)
        if index < total:
            pause("Enter — следующий вопрос", no_pause=no_pause)

    clear_screen()
    print_demo_line("[demo] итоговый рейтинг")
    print()
    print_total_rating(all_scores)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RAG with rewrite, CrossEncoder rerank, mode comparison."
    )
    parser.add_argument("--ask", metavar="QUESTION", help="Ask one question (Russian).")
    parser.add_argument(
        "--retrieve",
        metavar="QUESTION",
        help="Retrieve + rerank only (no LLM answer).",
    )
    parser.add_argument(
        "--compare-modes",
        metavar="QUESTION",
        help="Compare bare / rewrite / rerank / both on one question.",
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
    parser.add_argument(
        "--mode",
        choices=[m.value for m in PipelineMode],
        help="Pipeline mode (default: both).",
    )
    parser.add_argument("--no-rewrite", action="store_true", help="Skip query rewrite.")
    parser.add_argument("--no-rerank", action="store_true", help="Skip CrossEncoder rerank.")
    parser.add_argument("--retrieve-k", type=int, default=None, help="Top-K before rerank.")
    parser.add_argument("--rag-k", type=int, default=None, help="Top-K after filter.")
    parser.add_argument(
        "--min-score",
        type=float,
        default=None,
        help="CrossEncoder score threshold (default 0.15).",
    )
    args = parser.parse_args()

    if args.show_index:
        cmd_show_index()
        return

    if args.demo:
        cmd_demo(no_pause=args.no_pause, args=args)
        return

    if args.compare_modes:
        cmd_compare_modes(args.compare_modes, args)
        return

    if args.retrieve:
        cmd_retrieve(args.retrieve, args)
        return

    if args.ask:
        cmd_ask(args.ask, args)
        return

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
