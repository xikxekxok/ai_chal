"""MCP-клиент: три stdio-сервера burrow + trail + snout."""

from __future__ import annotations

import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Protocol

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Tool

DAY_DIR = Path(__file__).resolve().parent
BURROW_SCRIPT = DAY_DIR / "mcp" / "burrow_server.py"
TRAIL_SCRIPT = DAY_DIR / "mcp" / "trail_server.py"
SNOUT_SCRIPT = DAY_DIR / "mcp" / "snout_server.py"

BURROW_TOOLS = frozenset({"list_case_files", "read_case_file", "list_suspects"})
TRAIL_TOOLS = frozenset({"web_search", "read_page"})
SNOUT_TOOLS = frozenset({
    "add_clue",
    "list_clues",
    "test_theory",
    "build_timeline",
    "accuse",
    "clear_clues",
})


def preview_json(data: object, limit: int = 120) -> str:
    text = json.dumps(data, ensure_ascii=False)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


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
    llm_tools: list[dict[str, Any]] = []
    for tool in tools:
        llm_tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.inputSchema or {"type": "object", "properties": {}},
                },
            }
        )
    return llm_tools


class McpToolClient(Protocol):
    tools: list[Tool]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str: ...

    def llm_tools(self) -> list[dict[str, Any]]: ...

    def server_for(self, name: str) -> str: ...


class McpClient:
    def __init__(self, server_script: Path, server_label: str) -> None:
        self._server_script = server_script
        self._server_label = server_label
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self.tools: list[Tool] = []
        self.server_name = ""
        self.server_version = ""

    @property
    def label(self) -> str:
        return self._server_label

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


class MultiMcpClient:
    def __init__(
        self,
        *,
        burrow_script: Path | None = None,
        trail_script: Path | None = None,
        snout_script: Path | None = None,
    ) -> None:
        self._burrow_script = burrow_script or BURROW_SCRIPT
        self._trail_script = trail_script or TRAIL_SCRIPT
        self._snout_script = snout_script or SNOUT_SCRIPT
        self._stack: AsyncExitStack | None = None
        self.burrow: McpClient | None = None
        self.trail: McpClient | None = None
        self.snout: McpClient | None = None
        self.tools: list[Tool] = []
        self._tool_routes: dict[str, McpClient] = {}

    async def __aenter__(self) -> MultiMcpClient:
        self._stack = AsyncExitStack()
        self.burrow = await self._stack.enter_async_context(
            McpClient(self._burrow_script, "burrow")
        )
        self.trail = await self._stack.enter_async_context(
            McpClient(self._trail_script, "trail")
        )
        self.snout = await self._stack.enter_async_context(
            McpClient(self._snout_script, "snout")
        )
        self.tools = self.burrow.tools + self.trail.tools + self.snout.tools
        self._tool_routes.clear()
        for client in (self.burrow, self.trail, self.snout):
            for tool in client.tools:
                self._tool_routes[tool.name] = client
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = None
        self.burrow = None
        self.trail = None
        self.snout = None
        self.tools = []
        self._tool_routes.clear()

    @property
    def server_name(self) -> str:
        parts = []
        for client in (self.burrow, self.trail, self.snout):
            if client:
                parts.append(client.server_name)
        return "+".join(parts) if parts else "?"

    def server_for(self, name: str) -> str:
        client = self._tool_routes.get(name)
        return client.label if client else "?"

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        client = self._tool_routes.get(name)
        if client is None:
            return json.dumps({"error": f"unknown tool: {name}"}, ensure_ascii=False)
        return await client.call_tool(name, arguments or {})

    async def clear_clues(self) -> dict[str, Any]:
        raw = await self.call_tool("clear_clues", {})
        return json.loads(raw)

    def llm_tools(self) -> list[dict[str, Any]]:
        allowed = BURROW_TOOLS | TRAIL_TOOLS | (SNOUT_TOOLS - {"clear_clues"})
        filtered = [tool for tool in self.tools if tool.name in allowed]
        return tools_for_llm(filtered)
