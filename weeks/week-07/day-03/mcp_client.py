from __future__ import annotations

import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Tool

DAY_DIR = Path(__file__).resolve().parent
SERVER_SCRIPT = DAY_DIR / "mcp" / "server.py"


def preview_json(data: object, limit: int = 160) -> str:
    text = json.dumps(data, ensure_ascii=False)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def tool_result_text(result: Any) -> str:
    if result.structuredContent is not None:
        return json.dumps(result.structuredContent, ensure_ascii=False)
    if not result.content:
        return ""
    parts: list[str] = []
    for block in result.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


def tools_for_llm(tools: list[Tool]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema or {"type": "object", "properties": {}},
            },
        }
        for tool in tools
    ]


class McpClient:
    def __init__(self, server_script: Path | None = None) -> None:
        self._server_script = server_script or SERVER_SCRIPT
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self.tools: list[Tool] = []
        self.server_name = ""
        self.server_version = ""

    async def __aenter__(self) -> McpClient:
        self._stack = AsyncExitStack()
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(self._server_script)],
        )
        read, write = await self._stack.enter_async_context(
            stdio_client(params, errlog=open(os.devnull, "w"))
        )
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        init = await self._session.initialize()
        self.server_name = init.serverInfo.name
        self.server_version = init.serverInfo.version or "?"
        listed = await self._session.list_tools()
        self.tools = listed.tools
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = None
        self._session = None

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        if self._session is None:
            raise RuntimeError("MCP session is not open")
        result = await self._session.call_tool(name, arguments)
        text = tool_result_text(result)
        if result.isError:
            return json.dumps({"error": text}, ensure_ascii=False)
        return text

    def llm_tools(self) -> list[dict[str, Any]]:
        return tools_for_llm(self.tools)
