from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from agent import SupportAgent
from llm import load_llm_config
from mcp_client import McpClient, preview_json
from rag import load_kb

DAY_DIR = Path(__file__).resolve().parent
KB_DIR = DAY_DIR / "data" / "kb"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Day 33: support assistant with local RAG and MCP CRM.",
    )
    parser.add_argument("--demo", action="store_true", help="run video-friendly demo")
    parser.add_argument("--ask", help="ask the support assistant")
    parser.add_argument("--ticket", help="ticket id, for example T-1042")
    parser.add_argument("--show-kb", action="store_true", help="print local KB summary")
    parser.add_argument("--mcp-test", action="store_true", help="smoke-test local MCP server")
    return parser


def show_kb() -> None:
    docs = load_kb(KB_DIR)
    print("[demo] Local KB documents")
    for doc in docs:
        preview = " ".join(doc.text.split())[:120]
        print(f"[retrieve] {doc.doc_id}: {doc.title}")
        print(f"  preview: {preview}...")


async def run_mcp_test() -> None:
    print("[demo] MCP CRM smoke-test")
    async with McpClient() as mcp:
        print(f"[demo] connected: {mcp.server_name} v{mcp.server_version}")
        print(f"[tool] tools: {', '.join(tool.name for tool in mcp.tools)}")

        tickets_raw = await mcp.call_tool("list_tickets", {"status": "open"})
        tickets = json.loads(tickets_raw)
        print(f"[tool] list_tickets -> {preview_json(tickets)}")
        if int(tickets.get("count") or 0) < 1:
            print("[error] expected at least one open ticket", file=sys.stderr)
            raise SystemExit(1)

        ticket_raw = await mcp.call_tool("get_ticket", {"ticket_id": "T-1042"})
        ticket = json.loads(ticket_raw)
        print(f"[tool] get_ticket -> {preview_json(ticket)}")
        if ticket.get("ticket", {}).get("id") != "T-1042":
            print("[error] ticket T-1042 not found", file=sys.stderr)
            raise SystemExit(1)

        user_raw = await mcp.call_tool("get_user", {"user_id": "U-100"})
        user = json.loads(user_raw)
        print(f"[tool] get_user -> {preview_json(user)}")
        if user.get("user", {}).get("id") != "U-100":
            print("[error] user U-100 not found", file=sys.stderr)
            raise SystemExit(1)

    print("[demo] MCP CRM smoke-test OK")


def build_ticket_context(ticket: dict[str, object], user: dict[str, object] | None) -> str:
    lines = [
        "Контекст CRM:",
        json.dumps(ticket, ensure_ascii=False, indent=2),
    ]
    if user is not None:
        lines.extend(["Связанный пользователь:", json.dumps(user, ensure_ascii=False, indent=2)])
    return "\n".join(lines)


def print_user_turn(
    question: str,
    ticket_id: str | None,
    *,
    question_no: int | None = None,
) -> None:
    """Print the full user question before tools/answer (never truncated)."""
    tag = f"[user] Q{question_no}" if question_no is not None else "[user]"
    if ticket_id:
        print(f"{tag} ticket={ticket_id}: {question}", flush=True)
    else:
        print(f"{tag}: {question}", flush=True)


async def ask_assistant(
    question: str,
    ticket_id: str | None,
    *,
    question_no: int | None = None,
) -> None:
    print_user_turn(question, ticket_id, question_no=question_no)
    docs = load_kb(KB_DIR)
    config = load_llm_config()
    async with McpClient() as mcp:
        print(f"[demo] connected MCP: {mcp.server_name} v{mcp.server_version}")
        ticket_context = ""
        if ticket_id:
            ticket_payload = json.loads(await mcp.call_tool("get_ticket", {"ticket_id": ticket_id}))
            ticket = ticket_payload.get("ticket")
            if not isinstance(ticket, dict):
                print(f"[error] ticket {ticket_id} not found", file=sys.stderr)
                raise SystemExit(1)
            user_payload = json.loads(
                await mcp.call_tool("get_user", {"user_id": ticket["user_id"]})
            )
            user = user_payload.get("user")
            print(f"[tool] ticket context -> {preview_json(ticket_payload)}")
            print(f"[tool] user context -> {preview_json(user_payload)}")
            ticket_context = build_ticket_context(ticket, user if isinstance(user, dict) else None)

        user_prompt = question
        if ticket_context:
            user_prompt = f"{ticket_context}\n\nВопрос пользователя:\n{question}"

        agent = SupportAgent(config=config, kb_docs=docs, mcp=mcp)
        result = await agent.run(user_prompt)
        print("[agent] Ответ:")
        print(result.reply)
        print(
            f"[agent] tokens prompt={result.prompt_tokens} completion={result.completion_tokens}",
            flush=True,
        )


async def run_demo() -> None:
    print("[demo] Day 33: саппорт-ассистент NoteSync")
    print("[demo] план: показать KB -> проверить MCP -> спросить про SSO тикет")
    show_kb()
    print()
    await run_mcp_test()
    print()
    print("[demo] --- вопрос 1 ---")
    await ask_assistant("Почему не работает авторизация?", "T-1042", question_no=1)


def main() -> None:
    args = build_parser().parse_args()
    if args.show_kb:
        show_kb()
        return
    if args.mcp_test:
        asyncio.run(run_mcp_test())
        return
    if args.demo:
        asyncio.run(run_demo())
        return
    if args.ask:
        asyncio.run(ask_assistant(args.ask, args.ticket))
        return
    print("[error] Укажите один из режимов: --show-kb, --mcp-test, --ask, --demo", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
