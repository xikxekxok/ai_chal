"""Минимальный MCP-клиент: подключение к remote server и discovery tools."""

from __future__ import annotations

import asyncio
import json
import os
import sys

import httpx
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Tool

DEFAULT_URL = "https://mcp.deepwiki.com/mcp"


def print_demo_plan(url: str) -> None:
    print("[demo] MCP client — discovery tools (без вызова tools и без LLM)")
    print(f"[demo] сервер: DeepWiki MCP ({url})")
    print("[demo] план: connect → initialize → list_tools")


def print_tools(tools: list[Tool]) -> None:
    print(f"[mcp] tools ({len(tools)}):")
    for tool in tools:
        print(f"  - {tool.name}")
        if tool.description:
            print(f"    description:\n{tool.description}")
        else:
            print("    description: (нет)")
        if tool.inputSchema:
            print("    inputSchema:")
            print(json.dumps(tool.inputSchema, indent=2, ensure_ascii=False))
        else:
            print("    inputSchema: (нет)")
        if tool.outputSchema:
            print("    outputSchema:")
            print(json.dumps(tool.outputSchema, indent=2, ensure_ascii=False))
        else:
            print("    outputSchema: (нет)")
        print()


async def discover_tools(url: str) -> tuple[str, str, list[Tool]]:
    async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as http:
        async with streamable_http_client(url, http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                result = await session.list_tools()
                name = init.serverInfo.name
                version = init.serverInfo.version or "?"
                return name, version, result.tools


def main() -> None:
    url = os.environ.get("MCP_SERVER_URL", DEFAULT_URL).strip() or DEFAULT_URL
    print_demo_plan(url)

    print(f"[mcp] connecting: {url}")
    try:
        server_name, server_version, tools = asyncio.run(discover_tools(url))
    except httpx.TimeoutException:
        print("[error] таймаут при подключении к MCP-серверу", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPError as exc:
        print(f"[error] сетевая ошибка: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"[error] не удалось получить tools: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"[mcp] connected: {server_name} v{server_version}")
    if not tools:
        print("[error] сервер вернул пустой список tools", file=sys.stderr)
        sys.exit(1)

    print_tools(tools)


if __name__ == "__main__":
    main()
