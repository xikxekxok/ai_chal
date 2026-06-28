"""MCP web-search + scheduler + host/input split."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from agent import WebAgent
from host_ipc import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    HostServer,
    HostState,
    InboxItem,
    InputClient,
    enqueue_item,
)
from llm import LlmConfig, UsageTracker, load_llm_config
from mcp.types import Tool
from mcp_client import FALLBACK_PAGE_URL, MultiMcpClient, preview_json

DAY_DIR = Path(__file__).resolve().parent
SEARCH_QUERY = "Model Context Protocol"
SEARCH_MAX_RESULTS = 3
DEFAULT_TICK_SECONDS = 60
QUIT_WORDS = frozenset({"quit", "exit", "q"})


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


def format_due_prompt(due_payload: dict[str, object]) -> str:
    due_items = due_payload.get("due") or []
    if not isinstance(due_items, list) or not due_items:
        return "[scheduler] Запланированная задача без деталей."

    due_count = due_payload.get("due_count", len(due_items))
    lines = [
        f"[scheduler] Сработало запланированных задач: {due_count}.",
        "Выполни каждую инструкцию ниже (можно использовать web_search и read_page):",
    ]
    for index, item in enumerate(due_items, start=1):
        if not isinstance(item, dict):
            continue
        prompt = str(item.get("prompt") or "").strip()
        kind = str(item.get("kind") or "")
        job_id = str(item.get("id") or "")
        lines.append(f"{index}. [{kind} id={job_id}] {prompt}")
    return "\n".join(lines)


def parse_seed_once(raw: list[str] | None) -> tuple[int | None, str | None]:
    if not raw:
        return None, None
    try:
        delay = int(raw[0])
    except ValueError:
        print("[error] --seed-once SECONDS must be an integer", file=sys.stderr)
        sys.exit(1)
    if delay < 1:
        print("[error] --seed-once SECONDS must be >= 1", file=sys.stderr)
        sys.exit(1)
    prompt = raw[1].strip()
    if not prompt:
        print("[error] --seed-once PROMPT must not be empty", file=sys.stderr)
        sys.exit(1)
    return delay, prompt


async def run_clear() -> None:
    async with MultiMcpClient() as mcp:
        result = await mcp.clear_jobs()
        deleted = int(result.get("deleted") or 0)
        print(f"[scheduler] cleared {deleted} job(s)", flush=True)


async def seed_once(mcp: MultiMcpClient, delay_seconds: int, prompt: str) -> None:
    raw = await mcp.call_tool(
        "schedule_once",
        {"delay_seconds": delay_seconds, "prompt": prompt},
    )
    data = json.loads(raw)
    if "error" in data:
        print(f"[scheduler] seed error: {data['error']}", file=sys.stderr)
        sys.exit(1)
    print(
        f"[scheduler] seeded job_id={data.get('job_id')} "
        f"run_at={data.get('run_at')} preview={data.get('prompt_preview')!r}",
        flush=True,
    )


async def scheduler_ticker(
    mcp: MultiMcpClient,
    state: HostState,
    tick_seconds: int,
) -> None:
    while True:
        await asyncio.sleep(tick_seconds)
        due = await mcp.check_due()
        print(
            f"[scheduler] tick due_count={due.get('due_count', 0)} "
            f"pending={due.get('pending_total', 0)}",
            flush=True,
        )
        if int(due.get("due_count") or 0) <= 0:
            continue
        prompt = format_due_prompt(due)
        await enqueue_item(state, InboxItem("scheduler", prompt))


async def host_worker(agent: WebAgent, state: HostState) -> None:
    while True:
        item = await state.inbox.get()
        while item is not None:
            state.busy = True
            preview = item.text[:80] + ("…" if len(item.text) > 80 else "")
            print(f"[{item.source}] dispatch: {preview!r}", flush=True)
            result = await agent.run_turn(item.text)
            print(f"[agent] {result.reply}", flush=True)
            print_tokens(agent.tracker)
            state.busy = False
            try:
                item = state.inbox.get_nowait()
                print(
                    f"[host] next queued ({state.inbox.qsize()} pending)",
                    flush=True,
                )
            except asyncio.QueueEmpty:
                item = None


async def run_host(
    config: LlmConfig,
    *,
    bind_host: str,
    port: int,
    tick_seconds: int,
    seed_delay: int | None,
    seed_prompt: str | None,
) -> None:
    state = HostState()
    ipc_server = HostServer(host=bind_host, port=port, state=state)

    async with MultiMcpClient() as mcp:
        print(f"[mcp] connected: {mcp.server_name} v{mcp.server_version}")
        print(f"[agent] model: {config.model}")
        print(f"[scheduler] tick every {tick_seconds}s (UTC cron in scheduler MCP)")
        agent = WebAgent.create(config, mcp)

        if seed_delay is not None and seed_prompt:
            await seed_once(mcp, seed_delay, seed_prompt)

        await ipc_server.start()
        ticker = asyncio.create_task(scheduler_ticker(mcp, state, tick_seconds))
        worker = asyncio.create_task(host_worker(agent, state))
        try:
            await asyncio.gather(ticker, worker)
        finally:
            ticker.cancel()
            worker.cancel()
            await ipc_server.close()
            for task in (ticker, worker):
                try:
                    await task
                except asyncio.CancelledError:
                    pass


async def read_stdin_line() -> str | None:
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, lambda: input("Вы: ").strip())
    except EOFError:
        return None


async def run_input(*, host: str, port: int) -> None:
    client = await InputClient.connect(host=host, port=port)
    print(f"[input] connected to {host}:{port}", flush=True)
    print("[input] quit / exit / q — отключиться", flush=True)
    try:
        while True:
            line = await read_stdin_line()
            if line is None:
                print()
                break
            if not line:
                continue
            if line.lower() in QUIT_WORDS:
                await client.send_quit()
                break
            try:
                ack = await client.send_user(line)
            except ConnectionError as exc:
                print(f"[input] error: {exc}", file=sys.stderr)
                sys.exit(1)
            pending = int(ack.get("pending") or 0)
            if pending > 0:
                print(f"[input] sent (host queue: {pending})", flush=True)
    finally:
        await client.close()


async def run_mcp_test() -> None:
    print("[demo] Week 04 Day 03 — MCP smoke-test (web + scheduler, без LLM)")
    print(f"[demo] web: {DAY_DIR / 'mcp' / 'web_server.py'}")
    print(f"[demo] scheduler: {DAY_DIR / 'mcp' / 'scheduler_server.py'}")
    print("[demo] план: connect → scheduler → web_search → read_page")

    async with MultiMcpClient() as mcp:
        print(f"[mcp] connected: {mcp.server_name} v{mcp.server_version}")
        cleared = await mcp.clear_jobs()
        print(f"[scheduler] test setup: cleared {cleared.get('deleted', 0)} old job(s)")
        print_tools(mcp.tools)

        print("[mcp] call schedule_once delay_seconds=2 prompt='test reminder'")
        once_raw = await mcp.call_tool(
            "schedule_once",
            {"delay_seconds": 2, "prompt": "test reminder"},
        )
        once_data = json.loads(once_raw)
        print(f"[mcp] result schedule_once: {preview_json(once_data)}")
        if "error" in once_data:
            sys.exit(1)

        print("[mcp] call schedule_recurring cron='*/5 * * * *' prompt='periodic test'")
        recur_raw = await mcp.call_tool(
            "schedule_recurring",
            {"cron": "*/5 * * * *", "prompt": "periodic test"},
        )
        recur_data = json.loads(recur_raw)
        print(f"[mcp] result schedule_recurring: {preview_json(recur_data)}")
        if "error" in recur_data:
            sys.exit(1)

        list_raw = await mcp.call_tool("list_jobs", {})
        list_data = json.loads(list_raw)
        print(f"[mcp] result list_jobs: {preview_json(list_data, limit=200)}")
        if int(list_data.get("count") or 0) != 2:
            print("[error] expected list_jobs count=2", file=sys.stderr)
            sys.exit(1)

        recur_id = recur_data["job_id"]
        print(f"[mcp] call cancel_job job_id={recur_id!r}")
        cancel_raw = await mcp.call_tool("cancel_job", {"job_id": recur_id})
        cancel_data = json.loads(cancel_raw)
        print(f"[mcp] result cancel_job: {preview_json(cancel_data)}")
        if not cancel_data.get("cancelled"):
            sys.exit(1)

        list2_raw = await mcp.call_tool("list_jobs", {})
        list2_data = json.loads(list2_raw)
        if int(list2_data.get("count") or 0) != 1:
            print("[error] expected list_jobs count=1 after cancel", file=sys.stderr)
            sys.exit(1)

        print("[scheduler] sleep 3s before check_due")
        await asyncio.sleep(3)

        due1 = await mcp.check_due()
        print(f"[scheduler] check_due #1: {preview_json(due1, limit=200)}")
        if int(due1.get("due_count") or 0) != 1:
            print("[error] expected due_count=1 after sleep", file=sys.stderr)
            sys.exit(1)

        due2 = await mcp.check_due()
        print(f"[scheduler] check_due #2: {preview_json(due2, limit=200)}")
        if int(due2.get("due_count") or 0) != 0:
            print("[error] expected due_count=0 on second check", file=sys.stderr)
            sys.exit(1)
        if int(due2.get("completed_total") or 0) < 1:
            print("[error] expected completed_total >= 1", file=sys.stderr)
            sys.exit(1)

        print(f"[mcp] call web_search query={SEARCH_QUERY!r} max_results={SEARCH_MAX_RESULTS}")
        search_raw = await mcp.call_tool(
            "web_search",
            {"query": SEARCH_QUERY, "max_results": SEARCH_MAX_RESULTS},
        )
        search_data = json.loads(search_raw)
        print(f"[mcp] search count={search_data.get('count')}")

        results = search_data.get("results") or []
        page_url = results[0]["url"] if results else FALLBACK_PAGE_URL
        print(f"[mcp] call read_page url={page_url!r}")
        page_raw = await mcp.call_tool("read_page", {"url": page_url})
        page_data = json.loads(page_raw)
        print(f"[mcp] page title: {page_data.get('title', '')}")
        print(
            f"[mcp] page text ({page_data.get('chars')} chars"
            f"{', truncated' if page_data.get('truncated') else ''})"
        )

    print("[demo] smoke-test OK")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="MCP web-search + scheduler + host/input split.",
    )
    parser.add_argument("--mcp-test", action="store_true", help="smoke-test MCP без LLM")
    parser.add_argument("--clear", action="store_true", help="удалить все задачи scheduler")

    sub = parser.add_subparsers(dest="command")

    host_p = sub.add_parser("host", help="агент + scheduler + TCP-сервер (stdout only)")
    host_p.add_argument(
        "--bind",
        default=DEFAULT_HOST,
        help=f"адрес TCP-сервера (default {DEFAULT_HOST})",
    )
    host_p.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"порт TCP-сервера (default {DEFAULT_PORT})",
    )
    host_p.add_argument(
        "--tick-seconds",
        type=int,
        default=DEFAULT_TICK_SECONDS,
        help=f"интервал scheduler (default {DEFAULT_TICK_SECONDS})",
    )
    host_p.add_argument(
        "--seed-once",
        nargs=2,
        metavar=("SECONDS", "PROMPT"),
        help="при старте создать разовую задачу",
    )

    input_p = sub.add_parser("input", help="stdin → TCP-клиент host")
    input_p.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"адрес host (default {DEFAULT_HOST})",
    )
    input_p.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"порт host (default {DEFAULT_PORT})",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.mcp_test:
        asyncio.run(run_mcp_test())
        return

    if args.clear:
        asyncio.run(run_clear())
        return

    if args.command == "host":
        if args.tick_seconds < 1:
            print("[error] --tick-seconds must be >= 1", file=sys.stderr)
            sys.exit(1)
        if args.port < 1 or args.port > 65535:
            print("[error] --port must be 1..65535", file=sys.stderr)
            sys.exit(1)
        seed_delay, seed_prompt = parse_seed_once(args.seed_once)
        config = load_llm_config()
        try:
            asyncio.run(
                run_host(
                    config,
                    bind_host=args.bind,
                    port=args.port,
                    tick_seconds=args.tick_seconds,
                    seed_delay=seed_delay,
                    seed_prompt=seed_prompt,
                )
            )
        except OSError as exc:
            print(f"[error] host failed to bind {args.bind}:{args.port}: {exc}", file=sys.stderr)
            sys.exit(1)
        return

    if args.command == "input":
        asyncio.run(run_input(host=args.host, port=args.port))
        return

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
