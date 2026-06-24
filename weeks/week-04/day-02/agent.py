"""Тонкий агент с MCP tool-loop."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from llm import LlmConfig, UsageTracker, complete_message
from mcp_client import McpClient, preview_json

TOOL_LOOP_FUSE = 30
MAX_REPEAT_SAME_TOOL = 3

SYSTEM_PROMPT = """\
Ты помощник с доступом к веб-поиску и чтению страниц.
Используй web_search для поиска информации в интернете.
Используй read_page, чтобы прочитать конкретную страницу по URL.
Отвечай по-русски, кратко и по существу, опираясь на результаты tools.
Если поиск не дал результатов, скажи об этом честно.
"""


@dataclass
class TurnResult:
    reply: str
    prompt_tokens: int
    completion_tokens: int


def _tool_signature(name: str, arguments: dict[str, Any]) -> str:
    return f"{name}:{json.dumps(arguments, sort_keys=True, ensure_ascii=False)}"


@dataclass
class WebAgent:
    config: LlmConfig
    mcp: McpClient
    tracker: UsageTracker
    messages: list[dict[str, Any]]

    @classmethod
    def create(cls, config: LlmConfig, mcp: McpClient) -> WebAgent:
        return cls(
            config=config,
            mcp=mcp,
            tracker=UsageTracker(),
            messages=[{"role": "system", "content": SYSTEM_PROMPT}],
        )

    def _turn_usage_delta(self, usage_before: tuple[int, int]) -> tuple[int, int]:
        return (
            self.tracker.prompt_tokens - usage_before[0],
            self.tracker.completion_tokens - usage_before[1],
        )

    async def _finalize_without_tools(
        self,
        usage_before: tuple[int, int],
        *,
        reason: str,
    ) -> TurnResult:
        print(f"[agent] {reason}, финальный ответ без tools", flush=True)
        message, _ = complete_message(
            self.config,
            self.messages,
            tracker=self.tracker,
        )
        content = message.get("content") or (
            "Не удалось завершить ответ: слишком много вызовов tools."
        )
        self.messages.append({"role": "assistant", "content": content})
        prompt_delta, completion_delta = self._turn_usage_delta(usage_before)
        return TurnResult(
            reply=content,
            prompt_tokens=prompt_delta,
            completion_tokens=completion_delta,
        )

    async def run_turn(self, user_input: str) -> TurnResult:
        self.messages.append({"role": "user", "content": user_input})
        tools = self.mcp.llm_tools()
        usage_before = (self.tracker.prompt_tokens, self.tracker.completion_tokens)
        last_signature = ""
        repeat_count = 0

        for round_no in range(1, TOOL_LOOP_FUSE + 1):
            message, _ = complete_message(
                self.config,
                self.messages,
                tools=tools,
                tracker=self.tracker,
            )
            tool_calls = message.get("tool_calls")
            if tool_calls:
                self.messages.append(message)
                for call in tool_calls:
                    fn = call.get("function") or {}
                    name = fn.get("name") or ""
                    raw_args = fn.get("arguments") or "{}"
                    try:
                        arguments = json.loads(raw_args)
                    except json.JSONDecodeError:
                        arguments = {}
                    signature = _tool_signature(name, arguments)
                    if signature == last_signature:
                        repeat_count += 1
                    else:
                        last_signature = signature
                        repeat_count = 1
                    if repeat_count >= MAX_REPEAT_SAME_TOOL:
                        return await self._finalize_without_tools(
                            usage_before,
                            reason=(
                                f"зацикливание: {name} с теми же аргументами "
                                f"({repeat_count} раз подряд)"
                            ),
                        )
                    print(
                        f"[mcp] round {round_no} call {name}({preview_json(arguments)})",
                        flush=True,
                    )
                    tool_text = await self.mcp.call_tool(name, arguments)
                    try:
                        payload = json.loads(tool_text)
                        is_error = isinstance(payload, dict) and "error" in payload
                    except json.JSONDecodeError:
                        is_error = False
                    label = "error" if is_error else "result"
                    print(f"[mcp] {label} {name}: {preview_json(tool_text)}", flush=True)
                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id") or "",
                            "content": tool_text,
                        }
                    )
                continue

            content = message.get("content") or ""
            self.messages.append({"role": "assistant", "content": content})
            prompt_delta, completion_delta = self._turn_usage_delta(usage_before)
            return TurnResult(
                reply=content,
                prompt_tokens=prompt_delta,
                completion_tokens=completion_delta,
            )

        return await self._finalize_without_tools(
            usage_before,
            reason=f"fuse tool-loop ({TOOL_LOOP_FUSE} раундов)",
        )
