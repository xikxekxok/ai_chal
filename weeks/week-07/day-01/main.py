"""День 31: ассистент разработчика (RAG + MCP) для TaskBoard."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from agent import DevAssistant
from index import ensure_index, show_index_summary
from llm import LlmConfig, UsageTracker, load_llm_config
from mcp_client import McpClient
from paths import DAY_DIR, PROJECT_DIR

DEMO_QUESTIONS = [
    "Какая структура проекта TaskBoard?",
    "Какой эндпоинт создаёт задачу и какие поля в теле запроса?",
]


def print_tokens(tracker: UsageTracker) -> None:
    print(
        f"[tokens] calls={tracker.calls} | prompt={tracker.prompt_tokens} | "
        f"completion={tracker.completion_tokens} | ₽={tracker.cost_rub:.4f}"
    )


def print_tools(tools: list) -> None:
    print(f"[mcp] tools ({len(tools)}):")
    for tool in tools:
        print(f"  - {tool.name}: {tool.description or ''}")


async def run_mcp_test() -> None:
    print("[demo] MCP smoke: connect → list_tools → git_branch → list_files")
    print(f"[demo] server: {DAY_DIR / 'mcp' / 'server.py'}")
    async with McpClient() as mcp:
        print(f"[mcp] connected: {mcp.server_name} v{mcp.server_version}")
        print_tools(mcp.tools)
        branch_raw = await mcp.call_tool("git_branch", {})
        print(f"[mcp] git_branch: {branch_raw}")
        files_raw = await mcp.call_tool("list_files", {"subdir": "docs"})
        print(f"[mcp] list_files: {files_raw}")


async def run_help(
    config: LlmConfig,
    question: str,
    *,
    rebuild_index: bool = False,
) -> UsageTracker:
    index = ensure_index(rebuild=rebuild_index)
    chunks = index.get("chunks") or []
    async with McpClient() as client:
        print(f"[mcp] connected: {client.server_name} v{client.server_version}")
        assistant = DevAssistant.create(config, client, chunks)
        print(f"[help] {question}")
        result = await assistant.run_help(question)
        print(f"[agent] {result.reply}")
        print_tokens(assistant.tracker)
        return assistant.tracker


async def run_demo(config: LlmConfig) -> None:
    print("[demo] Week 07 Day 01 — ассистент разработчика (RAG + MCP)")
    print("[demo] корпус: project/README.md + project/docs/")
    print("[demo] план: index → mcp branch/files → 2× /help")
    print(f"[demo] project: {PROJECT_DIR}")

    index = ensure_index(rebuild=False)
    show_index_summary(index)
    chunks = index.get("chunks") or []

    async with McpClient() as client:
        print(f"[mcp] connected: {client.server_name} v{client.server_version}")
        print_tools(client.tools)
        branch_raw = await client.call_tool("git_branch", {})
        print(f"[mcp] git_branch: {branch_raw}")
        files_raw = await client.call_tool("list_files", {})
        files_data = json.loads(files_raw)
        print(f"[mcp] list_files count={files_data.get('count')}: {files_data.get('files')}")

        assistant = DevAssistant.create(config, client, chunks)
        for question in DEMO_QUESTIONS:
            print()
            print(f"[help] {question}")
            result = await assistant.run_help(question)
            print(f"[agent] {result.reply}")
        print()
        print_tokens(assistant.tracker)


async def run_chat(config: LlmConfig) -> None:
    print("Чат ассистента TaskBoard. Команды: /help <вопрос>, /quit")
    index = ensure_index(rebuild=False)
    chunks = index.get("chunks") or []
    async with McpClient() as client:
        print(f"[mcp] connected: {client.server_name} v{client.server_version}")
        assistant = DevAssistant.create(config, client, chunks)
        while True:
            try:
                line = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not line:
                continue
            if line in {"/quit", "/exit", "quit", "exit"}:
                break
            if line.startswith("/help"):
                question = line[len("/help") :].strip()
                if not question:
                    print("Использование: /help <вопрос>")
                    continue
            else:
                question = line
            result = await assistant.run_help(question)
            print(f"[agent] {result.reply}")
        print_tokens(assistant.tracker)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Developer assistant for TaskBoard (RAG + MCP).",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--index", action="store_true", help="построить RAG-индекс project/")
    mode.add_argument("--show-index", action="store_true", help="показать сводку индекса (без LLM)")
    mode.add_argument("--mcp-test", action="store_true", help="smoke MCP без LLM")
    mode.add_argument("--ask", metavar="QUESTION", help="one-shot /help вопрос")
    mode.add_argument("--chat", action="store_true", help="интерактив: /help <вопрос>")
    mode.add_argument("--demo", action="store_true", help="сценарий для видео")
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="с --ask/--demo: пересобрать индекс",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.index:
        ensure_index(rebuild=True)
        return 0

    if args.show_index:
        try:
            show_index_summary()
        except FileNotFoundError as exc:
            print(f"[error] {exc}", file=sys.stderr)
            return 1
        return 0

    if args.mcp_test:
        asyncio.run(run_mcp_test())
        return 0

    config = load_llm_config()

    if args.ask:
        asyncio.run(run_help(config, args.ask, rebuild_index=args.reindex))
        return 0

    if args.chat:
        asyncio.run(run_chat(config))
        return 0

    if args.demo:
        if args.reindex:
            ensure_index(rebuild=True)
        asyncio.run(run_demo(config))
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
