"""MCP pipeline: web_search → build_report → save_note."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from agent import PipelineAgent
from llm import LlmConfig, UsageTracker, load_llm_config
from mcp.types import Tool
from mcp_client import FALLBACK_PAGE_URL, McpClient, preview_json

DAY_DIR = Path(__file__).resolve().parent
NOTES_DIR = DAY_DIR / "data" / "notes"
SEARCH_QUERY = "Model Context Protocol"
SEARCH_MAX_RESULTS = 3
PREVIEW_CHARS = 300

DEFAULT_PROMPT = (
    "Найди три факта про Model Context Protocol в интернете, "
    "оформи отчёт и сохрани в файл mcp_facts.md"
)


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


def print_saved_preview(saved_path: str | None) -> None:
    if not saved_path:
        return
    path = DAY_DIR / saved_path
    if not path.is_file():
        print(f"[pipeline] saved path reported but file missing: {saved_path}", flush=True)
        return
    text = path.read_text(encoding="utf-8")
    print(f"[pipeline] saved: {saved_path} ({len(text)} chars)", flush=True)
    preview = text[:PREVIEW_CHARS]
    suffix = "…" if len(text) > PREVIEW_CHARS else ""
    print(f"[pipeline] preview:\n{preview}{suffix}", flush=True)


async def run_mcp_test() -> None:
    print("[mcp-test] Week 04 Day 04 — smoke (без LLM)")
    print(f"[mcp-test] server: {DAY_DIR / 'mcp' / 'server.py'}")
    print("[mcp-test] plan: connect → web_search → build_report → save_note")

    async with McpClient() as mcp:
        print(f"[mcp] connected: {mcp.server_name} v{mcp.server_version}")
        print_tools(mcp.tools)

        print(f"[mcp] call web_search query={SEARCH_QUERY!r} max_results={SEARCH_MAX_RESULTS}")
        search_raw = await mcp.call_tool(
            "web_search",
            {"query": SEARCH_QUERY, "max_results": SEARCH_MAX_RESULTS},
        )
        search_data = json.loads(search_raw)
        if "error" in search_data:
            print(f"[error] web_search: {search_data['error']}", file=sys.stderr)
            sys.exit(1)
        print(f"[mcp] search count={search_data.get('count')}")

        sources = [
            {"title": item.get("title", ""), "url": item.get("url", "")}
            for item in (search_data.get("results") or [])[:3]
            if isinstance(item, dict)
        ]
        report_args = {
            "topic": "Model Context Protocol",
            "findings": "- MCP — открытый протокол для tools и данных\n"
            "- Host подключает MCP servers через client\n"
            "- Tools имеют JSON schema для LLM",
            "sources": sources,
        }
        print(f"[mcp] call build_report {preview_json(report_args, limit=80)}")
        report_raw = await mcp.call_tool("build_report", report_args)
        report_data = json.loads(report_raw)
        if "error" in report_data:
            print(f"[error] build_report: {report_data['error']}", file=sys.stderr)
            sys.exit(1)
        markdown = str(report_data.get("markdown") or "")

        save_args = {"filename": "mcp_test.md", "content": markdown}
        print(f"[mcp] call save_note filename={save_args['filename']!r}")
        save_raw = await mcp.call_tool("save_note", save_args)
        save_data = json.loads(save_raw)
        if not save_data.get("ok"):
            print(f"[error] save_note: {save_data}", file=sys.stderr)
            sys.exit(1)

        saved = str(save_data.get("path") or "")
        print(f"[pipeline] saved: {saved}")
        if not (DAY_DIR / saved).is_file():
            print("[error] saved file not found", file=sys.stderr)
            sys.exit(1)

        page_url = sources[0]["url"] if sources else FALLBACK_PAGE_URL
        print(f"[mcp] call read_page url={page_url!r}")
        page_raw = await mcp.call_tool("read_page", {"url": page_url})
        page_data = json.loads(page_raw)
        if "error" in page_data:
            print(f"[mcp] read_page skipped: {page_data['error']}", flush=True)
        else:
            print(f"[mcp] page title: {page_data.get('title', '')}")


async def run_one_shot(config: LlmConfig, prompt: str) -> None:
    async with McpClient() as mcp:
        print(f"[mcp] connected: {mcp.server_name} v{mcp.server_version}")
        print(f"[agent] model: {config.model}")
        agent = PipelineAgent.create(config, mcp)

        print(f"[user] {prompt}")
        result = await agent.run_turn(prompt)
        print(f"[agent] {result.reply}")
        print_tokens(agent.tracker)
        print_saved_preview(result.saved_path)


async def run_chat(config: LlmConfig) -> None:
    async with McpClient() as mcp:
        print(f"[mcp] connected: {mcp.server_name} v{mcp.server_version}")
        print(f"[agent] model: {config.model}")
        print("[agent] интерактивный чат (quit / exit / q — выход)")
        agent = PipelineAgent.create(config, mcp)

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
            print(f"[agent] {result.reply}")
            print_tokens(agent.tracker)
            print_saved_preview(result.saved_path)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="MCP pipeline: search → report → save.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--mcp-test", action="store_true", help="smoke-test MCP без LLM")
    mode.add_argument("--chat", action="store_true", help="интерактивный чат")
    parser.add_argument(
        "prompt",
        nargs="*",
        help="one-shot запрос агенту (по умолчанию — DEFAULT_PROMPT)",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()

    if args.mcp_test:
        asyncio.run(run_mcp_test())
        return

    config = load_llm_config()
    if args.chat:
        asyncio.run(run_chat(config))
        return

    prompt = " ".join(args.prompt).strip() or DEFAULT_PROMPT
    asyncio.run(run_one_shot(config, prompt))


if __name__ == "__main__":
    main()
