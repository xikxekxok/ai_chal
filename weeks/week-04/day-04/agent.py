"""Агент с MCP tool-loop — композиция search → report → save."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from llm import LlmConfig, UsageTracker, complete_message
from mcp_client import McpClient, preview_json

TOOL_LOOP_FUSE = 30
MAX_REPEAT_SAME_TOOL = 3

SYSTEM_PROMPT = """\
Ты помощник с MCP-инструментами: web_search, read_page, build_report, save_note.

Когда пользователь просит найти информацию и сохранить в файл или заметку:
1. web_search — найди данные в интернете;
2. при необходимости read_page — прочитай конкретный URL из результатов;
3. build_report — оформи итог (topic, findings, sources из search);
4. save_note — сохрани markdown из build_report (поле markdown).

Если просят только поиск без сохранения — web_search и read_page достаточно.
Если просят сохранить — обязательно вызови build_report и save_note.
В финальном ответе укажи путь к файлу из save_note.
Не выдумывай факты: опирайся на результаты tools.
Отвечай по-русски, кратко и по существу.
"""


@dataclass
class TurnResult:
    reply: str
    prompt_tokens: int
    completion_tokens: int
    saved_path: str | None = None


def _tool_signature(name: str, arguments: dict[str, Any]) -> str:
    return f"{name}:{json.dumps(arguments, sort_keys=True, ensure_ascii=False)}"


def _extract_saved_path(tool_text: str) -> str | None:
    try:
        payload = json.loads(tool_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or not payload.get("ok"):
        return None
    path = payload.get("path")
    return str(path) if path else None


@dataclass
class PipelineAgent:
    config: LlmConfig
    mcp: McpClient
    tracker: UsageTracker
    messages: list[dict[str, Any]]
    last_saved_path: str | None = None

    @classmethod
    def create(cls, config: LlmConfig, mcp: McpClient) -> PipelineAgent:
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
            saved_path=self.last_saved_path,
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
                    saved = _extract_saved_path(tool_text)
                    if saved:
                        self.last_saved_path = saved
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
                saved_path=self.last_saved_path,
            )

        return await self._finalize_without_tools(
            usage_before,
            reason=f"fuse tool-loop ({TOOL_LOOP_FUSE} раундов)",
        )
