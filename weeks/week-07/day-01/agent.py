"""Ассистент: RAG-контекст + MCP tool-loop."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from llm import LlmConfig, UsageTracker, complete
from mcp_client import McpClient, preview_json
from rag import SYSTEM_PROMPT, build_user_message
from retrieve import print_hits, retrieve

TOOL_LOOP_FUSE = 12
MAX_REPEAT_SAME_TOOL = 3
DEFAULT_TOP_K = 4


@dataclass
class TurnResult:
    reply: str
    prompt_tokens: int
    completion_tokens: int


def _tool_signature(name: str, arguments: dict[str, Any]) -> str:
    return f"{name}:{json.dumps(arguments, sort_keys=True, ensure_ascii=False)}"


@dataclass
class DevAssistant:
    config: LlmConfig
    mcp: McpClient
    chunks: list[dict[str, Any]]
    tracker: UsageTracker
    messages: list[dict[str, Any]]
    top_k: int = DEFAULT_TOP_K

    @classmethod
    def create(
        cls,
        config: LlmConfig,
        mcp: McpClient,
        chunks: list[dict[str, Any]],
        *,
        top_k: int = DEFAULT_TOP_K,
    ) -> DevAssistant:
        return cls(
            config=config,
            mcp=mcp,
            chunks=chunks,
            tracker=UsageTracker(),
            messages=[{"role": "system", "content": SYSTEM_PROMPT}],
            top_k=top_k,
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
        message, _ = complete(self.config, self.messages, tracker=self.tracker)
        content = message.get("content") or "Не удалось завершить ответ."
        self.messages.append({"role": "assistant", "content": content})
        prompt_delta, completion_delta = self._turn_usage_delta(usage_before)
        return TurnResult(
            reply=content,
            prompt_tokens=prompt_delta,
            completion_tokens=completion_delta,
        )

    async def run_help(self, question: str) -> TurnResult:
        hits = retrieve(question, self.chunks, top_k=self.top_k)
        print_hits(hits)
        user_message = build_user_message(question, hits)
        self.messages.append({"role": "user", "content": user_message})
        tools = self.mcp.llm_tools()
        usage_before = (self.tracker.prompt_tokens, self.tracker.completion_tokens)
        last_signature = ""
        repeat_count = 0

        for round_no in range(1, TOOL_LOOP_FUSE + 1):
            message, _ = complete(
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
                        if not isinstance(arguments, dict):
                            arguments = {}
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
                    result_text = await self.mcp.call_tool(name, arguments)
                    preview = result_text if len(result_text) <= 200 else result_text[:199] + "…"
                    print(f"[mcp] result: {preview}", flush=True)
                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id") or name,
                            "content": result_text,
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
            reason=f"fuse: {TOOL_LOOP_FUSE} раундов",
        )
