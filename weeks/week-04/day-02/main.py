"""MCP web-search server + агент с tool-loop."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from agent import WebAgent
from console_out import (
    WAIT_DEMO_START,
    clear_screen,
    typewriter_print,
    wait_and_clear,
)
from llm import LlmConfig, UsageTracker, load_llm_config
from mcp.types import Tool
from mcp_client import FALLBACK_PAGE_URL, McpClient

DAY_DIR = Path(__file__).resolve().parent
SEARCH_QUERY = "Model Context Protocol"
SEARCH_MAX_RESULTS = 3
PREVIEW_CHARS = 300

DEMO_TURNS = [
    "Что такое Model Context Protocol? Найди в интернете и кратко объясни.",
    "Прочитай официальную страницу MCP и назови три ключевые идеи.",
]


def print_tools(tools: list[Tool]) -> None:
    print(f"[mcp] tools ({len(tools)}):")
    for tool in tools:
        print(f"  - {tool.name}")
        if tool.description:
            print(f"    description: {tool.description}")
        if tool.inputSchema:
            print("    inputSchema:")
            print(json.dumps(tool.inputSchema, indent=2, ensure_ascii=False))
        print()


def print_tokens(tracker: UsageTracker) -> None:
    print(
        f"[tokens] calls={tracker.calls} | prompt={tracker.prompt_tokens} | "
        f"completion={tracker.completion_tokens} | ₽={tracker.cost_rub:.4f}"
    )


def print_demo_intro(*, with_agent: bool) -> None:
    print("[demo] Week 04 Day 02 — MCP web-search")
    if with_agent:
        print("[demo] агент + локальный MCP (web_search, read_page)")
        print(f"[demo] план: connect → {len(DEMO_TURNS)} хода диалога")
    else:
        print("[demo] smoke-test MCP без LLM")
        print("[demo] план: connect → list_tools → web_search → read_page")
    print(f"[demo] сервер: {DAY_DIR / 'mcp' / 'server.py'}")


async def run_mcp_test() -> None:
    print_demo_intro(with_agent=False)
    async with McpClient() as mcp:
        print(f"[mcp] connected: {mcp.server_name} v{mcp.server_version}")
        print_tools(mcp.tools)

        print(f"[mcp] call web_search query={SEARCH_QUERY!r} max_results={SEARCH_MAX_RESULTS}")
        search_raw = await mcp.call_tool(
            "web_search",
            {"query": SEARCH_QUERY, "max_results": SEARCH_MAX_RESULTS},
        )
        search_data = json.loads(search_raw)
        print(f"[mcp] search count={search_data.get('count')}")
        for index, item in enumerate(search_data.get("results") or [], start=1):
            print(f"  {index}. {item.get('title', '')}")
            print(f"     {item.get('url', '')}")
            snippet = (item.get("snippet") or "").replace("\n", " ")
            if snippet:
                clipped = snippet[:PREVIEW_CHARS]
                suffix = "…" if len(snippet) > PREVIEW_CHARS else ""
                print(f"     {clipped}{suffix}")

        results = search_data.get("results") or []
        page_url = results[0]["url"] if results else FALLBACK_PAGE_URL
        print(f"[mcp] call read_page url={page_url!r}")
        page_raw = await mcp.call_tool("read_page", {"url": page_url})
        page_data = json.loads(page_raw)
        print(f"[mcp] page title: {page_data.get('title', '')}")
        print(
            f"[mcp] page text ({page_data.get('chars')} chars"
            f"{', truncated' if page_data.get('truncated') else ''}):"
        )
        text = page_data.get("text") or ""
        preview = text[:PREVIEW_CHARS]
        print(f"  {preview}{'…' if len(text) > PREVIEW_CHARS else ''}")


async def run_demo(config: LlmConfig, *, streaming: bool, video: bool) -> None:
    print_demo_intro(with_agent=True)
    if video:
        clear_screen()
        wait_and_clear(WAIT_DEMO_START)

    async with McpClient() as mcp:
        print(f"[mcp] connected: {mcp.server_name} v{mcp.server_version}")
        print_tools(mcp.tools)
        agent = WebAgent.create(config, mcp)

        for index, user_text in enumerate(DEMO_TURNS):
            if video:
                clear_screen()
            if streaming:
                typewriter_print("[user] ", user_text)
            else:
                print(f"[user] {user_text}")

            result = await agent.run_turn(user_text)
            if streaming:
                typewriter_print("[agent] ", result.reply)
            else:
                print(f"[agent] {result.reply}")
            print_tokens(agent.tracker)

            if video and index + 1 < len(DEMO_TURNS):
                wait_and_clear()


async def run_chat(config: LlmConfig, *, streaming: bool) -> None:
    async with McpClient() as mcp:
        print(f"[mcp] connected: {mcp.server_name} v{mcp.server_version}")
        print(f"[agent] model: {config.model}")
        print("[agent] интерактивный чат (quit / exit / q — выход)")
        agent = WebAgent.create(config, mcp)

        while True:
            try:
                user_input = input("Вы: ").strip()
            except EOFError:
                print()
                break
            if not user_input:
                continue
            if user_input.lower() in {"quit", "exit", "q"}:
                break

            result = await agent.run_turn(user_input)
            if streaming:
                typewriter_print("[agent] ", result.reply)
            else:
                print(f"[agent] {result.reply}")
            print_tokens(agent.tracker)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MCP web-search + агент.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--mcp-test", action="store_true", help="smoke-test MCP без LLM")
    mode.add_argument("--demo", action="store_true", help="сценарий для видео")
    mode.add_argument("--chat", action="store_true", help="интерактивный чат")
    parser.add_argument(
        "--video",
        action="store_true",
        help="с --demo: один шаг на экран, any-key между шагами",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="реплики целиком, без typewriter",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    streaming = not args.no_stream

    if args.mcp_test:
        asyncio.run(run_mcp_test())
        return

    if args.chat:
        config = load_llm_config()
        asyncio.run(run_chat(config, streaming=streaming))
        return

    if args.demo or not (args.mcp_test or args.chat):
        config = load_llm_config()
        asyncio.run(run_demo(config, streaming=streaming, video=args.video))
        return


if __name__ == "__main__":
    main()
