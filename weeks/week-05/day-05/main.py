#!/usr/bin/env python3
"""RAG chat with dialog history, sources on every turn."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from chat import RagChat, print_response
from console_out import pause, print_index_line, print_tagged
from embeddings import check_ollama
from history import clear_history
from paths import DAY_DIR, HISTORY_PATH, INDEX_PATH
from pipeline import PipelineConfig
from run_log import get_run_log, init_run_log
from scenarios import ALL_SCENARIO_KEYS, SCENARIOS
from store import load_index


def format_size_mb(path: Any) -> str:
    size = path.stat().st_size
    return f"{size / (1024 * 1024):.1f} MB"


def _build_config(args: argparse.Namespace) -> PipelineConfig:
    return PipelineConfig(
        retrieve_k=args.retrieve_k,
        rag_k=args.rag_k,
        min_score=args.min_score,
    )


def print_store_status(chat: RagChat) -> None:
    count = chat.turn_count
    if count == 0:
        print("[store] история: новая сессия")
    else:
        print(
            f"[store] история: {count} сообщений "
            f"(восстановлено из {chat.history_path.name})"
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


def cmd_clear() -> None:
    if HISTORY_PATH.is_file():
        clear_history()
        print(f"[store] удалён {HISTORY_PATH.name}")
    else:
        print("[store] история уже пуста")


def cmd_chat(chat: RagChat) -> None:
    print_store_status(chat)
    print("[agent] интерактивный RAG-чат (quit / exit — выход)")
    while True:
        try:
            user_input = input("вы: ").strip()
        except EOFError:
            print()
            break
        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit", "q"}:
            break
        result = chat.run_turn(user_input)
        print_response(result)
        print_tagged("store", f"сохранено {chat.turn_count} сообщений")


def _print_scenario_plan(scenario) -> None:
    print_tagged("scenario", "вопросы пользователя (RU):")
    for idx, message in enumerate(scenario.messages, start=1):
        print(f"  {idx:2}. {message}")
    print()


def _run_scenario(
    chat: RagChat,
    key: str,
    *,
    index: int,
    total: int,
    no_pause: bool,
) -> None:
    scenario = SCENARIOS[key]
    chat.clear()
    log = get_run_log()
    log.section("scenario_start")
    log.kv("key", key, indent=1)
    log.kv("title", scenario.title, indent=1)
    log.kv("turns", len(scenario.messages), indent=1)
    log.blank()
    print_tagged("scenario", f"{'=' * 60}")
    print_tagged("scenario", f"сценарий {index}/{total}: {scenario.title}")
    print_tagged("scenario", f"реплик: {len(scenario.messages)}")
    _print_scenario_plan(scenario)
    pause("Enter — начать сценарий", no_pause=no_pause)

    for turn_idx, message in enumerate(scenario.messages, start=1):
        print_tagged("scenario", f"ход {turn_idx}/{len(scenario.messages)}")
        result = chat.run_turn(message)
        print_response(result)
        print_tagged("store", f"сохранено {chat.turn_count} сообщений")
        if turn_idx < len(scenario.messages):
            pause("Enter — следующая реплика", no_pause=no_pause)
    print_tagged("scenario", f"сценарий {index}/{total} завершён")
    print()


def cmd_scenario(chat: RagChat, choice: str, *, no_pause: bool) -> None:
    keys = list(ALL_SCENARIO_KEYS) if choice == "all" else [choice]
    total = len(keys)
    total_turns = sum(len(SCENARIOS[k].messages) for k in keys)
    print_tagged(
        "scenario",
        f"режим: {choice} · сценариев: {total} · реплик всего: {total_turns}",
    )
    print()
    for index, key in enumerate(keys, start=1):
        _run_scenario(chat, key, index=index, total=total, no_pause=no_pause)


def cmd_ask(chat: RagChat, question: str) -> None:
    print_store_status(chat)
    result = chat.run_turn(question)
    print_response(result)
    print_tagged("store", f"сохранено {chat.turn_count} сообщений")


def _run_mode_name(args: argparse.Namespace) -> str:
    if args.scenario:
        return f"scenario-{args.scenario}"
    if args.chat:
        return "chat"
    if args.ask:
        return "ask"
    return "run"


def _init_agent_log(args: argparse.Namespace, *, chunks_count: int) -> None:
    mode = _run_mode_name(args)
    log = init_run_log(
        mode,
        retrieve_k=args.retrieve_k,
        rag_k=args.rag_k,
        min_score=args.min_score,
        chunks_in_index=chunks_count,
        no_pause=args.no_pause,
    )
    rel = log.path.relative_to(DAY_DIR)
    print_tagged("log", f"файл: {rel}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG chat with history and sources.")
    parser.add_argument("--chat", action="store_true", help="Interactive chat.")
    parser.add_argument(
        "--scenario",
        choices=["1", "2", "all"],
        help="Run scripted scenario (12 turns each).",
    )
    parser.add_argument("--ask", metavar="QUESTION", help="Single question (Russian).")
    parser.add_argument("--clear", action="store_true", help="Clear chat history.")
    parser.add_argument(
        "--show-index",
        action="store_true",
        help="Show index stats (no Ollama/LLM).",
    )
    parser.add_argument(
        "--analyze-last-run",
        action="store_true",
        help="Summarize latest logs/*.log for failures (no API).",
    )
    parser.add_argument("--no-pause", action="store_true", help="Scenario without pauses.")
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

    if args.analyze_last_run:
        from analyze_run import run_analysis

        sys.exit(run_analysis())
        return

    if args.clear and not any((args.chat, args.scenario, args.ask)):
        cmd_clear()
        return

    data = load_index()
    check_ollama()
    cfg = _build_config(args)
    _init_agent_log(args, chunks_count=len(data["chunks"]))
    chat = RagChat(data["chunks"], cfg)

    if args.clear:
        chat.clear()
        print(f"[store] удалён {HISTORY_PATH.name}")

    if args.scenario:
        cmd_scenario(chat, args.scenario, no_pause=args.no_pause)
        return

    if args.chat:
        cmd_chat(chat)
        return

    if args.ask:
        cmd_ask(chat, args.ask)
        return

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
