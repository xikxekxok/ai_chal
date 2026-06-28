"""MCP-клиент: stdio subprocess, list_tools, call_tool; MultiMcpClient для двух серверов."""

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
WEB_SERVER_SCRIPT = DAY_DIR / "mcp" / "web_server.py"
SCHEDULER_SERVER_SCRIPT = DAY_DIR / "mcp" / "scheduler_server.py"
FALLBACK_PAGE_URL = "https://modelcontextprotocol.io/"

WEB_TOOL_NAMES = frozenset({"web_search", "read_page"})
SCHEDULER_LLM_TOOL_NAMES = frozenset({
    "schedule_once",
    "schedule_recurring",
    "list_jobs",
    "cancel_job",
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
    server_name: str
    server_version: str

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str: ...

    def llm_tools(self) -> list[dict[str, Any]]: ...


class McpClient:
    def __init__(self, server_script: Path) -> None:
        self._server_script = server_script
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


class MultiMcpClient:
    def __init__(
        self,
        *,
        web_script: Path | None = None,
        scheduler_script: Path | None = None,
    ) -> None:
        self._web_script = web_script or WEB_SERVER_SCRIPT
        self._scheduler_script = scheduler_script or SCHEDULER_SERVER_SCRIPT
        self._stack: AsyncExitStack | None = None
        self.web: McpClient | None = None
        self.scheduler: McpClient | None = None
        self.tools: list[Tool] = []
        self._tool_routes: dict[str, McpClient] = {}

    async def __aenter__(self) -> MultiMcpClient:
        self._stack = AsyncExitStack()
        self.web = await self._stack.enter_async_context(McpClient(self._web_script))
        self.scheduler = await self._stack.enter_async_context(
            McpClient(self._scheduler_script)
        )
        self.tools = self.web.tools + self.scheduler.tools
        self._tool_routes.clear()
        for tool in self.web.tools:
            self._tool_routes[tool.name] = self.web
        for tool in self.scheduler.tools:
            self._tool_routes[tool.name] = self.scheduler
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = None
        self.web = None
        self.scheduler = None
        self.tools = []
        self._tool_routes.clear()

    @property
    def server_name(self) -> str:
        web_name = self.web.server_name if self.web else "?"
        sched_name = self.scheduler.server_name if self.scheduler else "?"
        return f"{web_name}+{sched_name}"

    @property
    def server_version(self) -> str:
        web_ver = self.web.server_version if self.web else "?"
        sched_ver = self.scheduler.server_version if self.scheduler else "?"
        return f"{web_ver}+{sched_ver}"

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        client = self._tool_routes.get(name)
        if client is None:
            return json.dumps({"error": f"unknown tool: {name}"}, ensure_ascii=False)
        return await client.call_tool(name, arguments or {})

    async def check_due(self) -> dict[str, Any]:
        raw = await self.call_tool("check_due", {})
        return json.loads(raw)

    async def clear_jobs(self) -> dict[str, Any]:
        raw = await self.call_tool("clear_jobs", {})
        return json.loads(raw)

    def llm_tools(self) -> list[dict[str, Any]]:
        allowed = WEB_TOOL_NAMES | SCHEDULER_LLM_TOOL_NAMES
        filtered = [tool for tool in self.tools if tool.name in allowed]
        return tools_for_llm(filtered)
