"""Opossum detective: три MCP-сервера, дело пропавшего шара Тофика."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from agent import HolmesAgent
from console_out import (
    drain_display,
    enable_pager,
    pager_enabled,
    print_demo_line,
    print_mcp,
    print_reply,
    print_tagged,
    print_tokens_line,
    shutdown_display,
    style,
    wait_and_clear,
)
from llm import LlmConfig, UsageTracker, load_llm_config
from mcp.types import Tool
from mcp_client import MultiMcpClient
from narration import format_mcp_call, reveal_tool_result

DAY_DIR = Path(__file__).resolve().parent

DEFAULT_PROMPT = (
    "Шерлок, расследуй дело missing_ball от 14.05.2024: пропал шар Тофика. "
    "Прочитай весь архив, собери улики, проверь версии, назови виновника."
)

DEMO_PROMPT = (
    "Шерлок! 14 мая пропал шар Тофика — съёмка «на шаре» под угрозой. "
    "Лестрейд приложил отчёт, показания, журнал беседки и акт осмотра сарая. "
    "Разберись: архив, улики, проверь всех, назови виновника."
)

QUIT_WORDS = frozenset({"quit", "exit", "q"})


def print_demo_intro() -> None:
    print_demo_line("[demo] === Дело missing_ball: пропал шар Тофика ===")
    print_demo_line("[demo] Три MCP-сервера: burrow (архив) + trail (веб) + snout (дедукция).")
    print_demo_line("[demo] Один запуск: Ватсон → Шерлок ведёт расследование до accuse.")
    print_demo_line(
        "[demo] Цвета: holmes=cyan, trail=green, clue=yellow, verdict=red (NO_COLOR=1 — выкл.)"
    )
    print_demo_line("[demo] Постраничный: --pager/--video; агент в фоне, Space — листать.")


def print_tools(tools: list[Tool]) -> None:
    print_tagged("mcp", f"tools ({len(tools)}):")
    for tool in tools:
        print(f"  {style('•', '90')} {tool.name}")


def print_tokens(tracker: UsageTracker, *, prefix: str = "") -> None:
    print_tokens_line(
        f"[tokens]{prefix} calls={tracker.calls} | prompt={tracker.prompt_tokens} | "
        f"completion={tracker.completion_tokens} | ₽={tracker.cost_rub:.4f}"
    )


async def run_mcp_test() -> None:
    try:
        print_tagged("mcp-test", "Week 04 Day 05 — smoke (без LLM)")
        print_tagged(
            "mcp-test",
            "plan: burrow (4 файла) → clues + trail → test crow/sasha → accuse(pete)",
        )

        async with MultiMcpClient() as mcp:
            print_tagged("mcp", f"connected: {mcp.server_name}")
            print_tools(mcp.tools)

            print_mcp("burrow", "list_case_files()")
            raw = await mcp.call_tool("list_case_files", {})
            files = json.loads(raw)
            assert files.get("victim") == "Тофик"
            assert len(files.get("files") or []) >= 4
            reveal_tool_result("burrow", "list_case_files", files)

            for file_id in ("yard_report", "witness_marta", "gazebo_log", "shed_findings"):
                print_mcp("burrow", f'read_case_file(file_id="{file_id}")')
                doc = json.loads(await mcp.call_tool("read_case_file", {"file_id": file_id}))
                reveal_tool_result(
                    "burrow", "read_case_file", doc, arguments={"file_id": file_id}
                )

            print_mcp("burrow", "list_suspects()")
            dossier = json.loads(await mcp.call_tool("list_suspects", {}))
            reveal_tool_result("burrow", "list_suspects", dossier)

            clues = [
                {
                    "fact": "В 18:38 у кустов шуршание и тяжёлая ноша к сараю",
                    "source": "witness_marta",
                    "tags": ["witness_marta", "near_bushes", "time:18:38"],
                },
                {
                    "fact": "Журнал: Доцент до 18:20 у беседки, к 18:45 место пусто",
                    "source": "gazebo_log",
                    "tags": ["dozent_alibi_broken", "time:18:45"],
                },
                {
                    "fact": "У сарая бахрома театрального плаща и следы опоссума",
                    "source": "shed_findings",
                    "tags": ["shed_traces", "fiber_theater"],
                },
                {
                    "fact": "Метеосводка: вечером 14.05 в Подольске штиль, без дождя",
                    "source": "trail-weather-check",
                    "tags": ["weather_confirmed"],
                },
                {
                    "fact": "Чек лавки: Саша в Подольске 18:28–19:00",
                    "source": "yard_report",
                    "tags": ["sasha_alibi", "time:18:28"],
                },
                {
                    "fact": "Барбос на цепи, лай в 18:35",
                    "source": "yard_report",
                    "tags": ["barbos_chained", "time:18:35"],
                },
                {
                    "fact": "Фитбол ~0.5–1 кг — ворона не унесёт",
                    "source": "trail-weight-check",
                    "tags": ["crow_too_heavy"],
                },
            ]
            for item in clues:
                print_mcp("snout", format_mcp_call("add_clue", item))
                result = json.loads(await mcp.call_tool("add_clue", item))
                if "error" in result:
                    print(f"[error] add_clue: {result}", file=sys.stderr)
                    sys.exit(1)
                reveal_tool_result("snout", "add_clue", result, arguments=item)

            print_mcp("snout", 'test_theory(suspect_id="sasha")')
            sasha = json.loads(await mcp.call_tool("test_theory", {"suspect_id": "sasha"}))
            if sasha.get("verdict") != "busted":
                print(f"[error] expected sasha busted, got {sasha}", file=sys.stderr)
                sys.exit(1)
            reveal_tool_result("snout", "test_theory", sasha)

            print_mcp("snout", 'test_theory(suspect_id="pete")')
            theory = json.loads(await mcp.call_tool("test_theory", {"suspect_id": "pete"}))
            if theory.get("verdict") != "supported":
                print(f"[error] expected supported, got {theory}", file=sys.stderr)
                sys.exit(1)
            reveal_tool_result("snout", "test_theory", theory)

            print_mcp("snout", 'test_theory(suspect_id="crow")')
            crow = json.loads(await mcp.call_tool("test_theory", {"suspect_id": "crow"}))
            if crow.get("verdict") != "busted":
                print(f"[error] expected crow busted, got {crow}", file=sys.stderr)
                sys.exit(1)
            reveal_tool_result("snout", "test_theory", crow)

            print_mcp("snout", 'accuse(suspect_id="pete")')
            verdict = json.loads(await mcp.call_tool("accuse", {"suspect_id": "pete"}))
            if not verdict.get("ok"):
                print(f"[error] accuse failed: {verdict}", file=sys.stderr)
                sys.exit(1)
            reveal_tool_result("snout", "accuse", verdict)
    finally:
        await _finish_pager()


async def run_clear() -> None:
    async with MultiMcpClient() as mcp:
        result = await mcp.clear_clues()
        print(f"[snout] cleared {result.get('deleted', 0)} clue(s)", flush=True)


async def _finish_pager() -> None:
    if pager_enabled():
        drain_display()
        shutdown_display()


async def run_one_shot(config: LlmConfig, prompt: str, *, stream: bool) -> None:
    try:
        async with MultiMcpClient() as mcp:
            print_tagged("mcp", f"connected: {mcp.server_name}")
            print_tagged("holmes", f"model: {config.model}")
            agent = HolmesAgent.create(config, mcp)

            print_reply("watson", prompt, stream=stream)
            result = await agent.run_turn(prompt)
            print_reply("holmes", result.reply, stream=stream)
            print_tokens(agent.tracker)
            if result.accused:
                print_tagged("verdict", f"обвинён: {result.accused}")
    finally:
        await _finish_pager()


async def run_demo(config: LlmConfig, *, stream: bool, video: bool) -> None:
    if video:
        wait_and_clear("\n[demo] ── готовы? Любая клавиша → начало ──")
    print_demo_intro()

    try:
        async with MultiMcpClient() as mcp:
            print_tagged("mcp", f"connected: {mcp.server_name}")
            print_tagged("holmes", f"model: {config.model}")
            agent = HolmesAgent.create(config, mcp)

            print_reply("watson", DEMO_PROMPT, stream=stream)
            result = await agent.run_turn(DEMO_PROMPT)
            print_reply("holmes", result.reply, stream=stream)
            print_tokens(agent.tracker)
            if result.accused:
                print_tagged("verdict", f"обвинён: {result.accused}")
    finally:
        await _finish_pager()


async def run_chat(config: LlmConfig, *, stream: bool) -> None:
    async with MultiMcpClient() as mcp:
        print_tagged("mcp", f"connected: {mcp.server_name}")
        print_tagged("holmes", f"model: {config.model}")
        print_tagged("watson", "интерактив (quit / exit / q — выход)")
        agent = HolmesAgent.create(config, mcp)

        while True:
            try:
                user_input = input("Ватсон: ").strip()
            except EOFError:
                print()
                break
            if not user_input:
                continue
            if user_input.lower() in QUIT_WORDS:
                break

            result = await agent.run_turn(user_input)
            print_reply("holmes", result.reply, stream=stream)
            print_tokens(agent.tracker)
            if result.accused:
                print_tagged("verdict", f"обвинён: {result.accused}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Opossum detective MCP orchestration (дело Тофика).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--mcp-test", action="store_true", help="smoke-test MCP без LLM")
    mode.add_argument("--demo", action="store_true", help="one-shot demo для видео")
    mode.add_argument("--chat", action="store_true", help="интерактивный чат")
    mode.add_argument("--clear", action="store_true", help="очистить доску улик")
    parser.add_argument(
        "--video",
        action="store_true",
        help="для видео: --pager + пауза перед стартом",
    )
    parser.add_argument(
        "--pager",
        action="store_true",
        help="постраничный вывод (Space/Enter — далее, q — выход)",
    )
    parser.add_argument(
        "--no-pager-clear",
        action="store_true",
        help="не очищать экран между страницами (листание вниз)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="без ANSI-цветов (или NO_COLOR=1)",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="реплики целиком, без typewriter",
    )
    parser.add_argument(
        "prompt",
        nargs="*",
        help="one-shot запрос (по умолчанию — DEFAULT_PROMPT)",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    if args.no_color:
        os.environ["NO_COLOR"] = "1"
    if args.pager or args.video:
        enable_pager(clear=not args.no_pager_clear)
    stream = not args.no_stream and not (args.pager or args.video)

    if args.mcp_test:
        asyncio.run(run_mcp_test())
        return

    if args.clear:
        asyncio.run(run_clear())
        return

    if args.demo:
        config = load_llm_config()
        asyncio.run(run_demo(config, stream=stream, video=args.video))
        return

    if args.chat:
        config = load_llm_config()
        asyncio.run(run_chat(config, stream=stream))
        return

    config = load_llm_config()
    prompt = " ".join(args.prompt).strip() or DEFAULT_PROMPT
    asyncio.run(run_one_shot(config, prompt, stream=stream))


if __name__ == "__main__":
    main()
