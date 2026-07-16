"""Simple file assistant with local tool loop."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from llm import LlmConfig, UsageTracker, complete
from tools import ToolExecutor, ToolRegistry

SYSTEM_PROMPT = """You are an AI file assistant working inside a sandbox project.

Rules:
- Solve the user's task by using tools when needed.
- Use only relative sandbox paths like README.md or src/app.py.
- Never invent file contents when you can inspect them first.
- Before editing a file, inspect enough code to make the change grounded.
- The only writable tool is write_file; use it with full file content.
- Stay concise in final answers and mention concrete files changed.
"""

TOOL_LOOP_FUSE = 10
MAX_REPEAT_SAME_TOOL = 3


@dataclass(slots=True)
class AgentResult:
    reply: str
    tool_calls: int
    tracker: UsageTracker


def _signature(name: str, arguments: dict[str, Any]) -> str:
    return f"{name}:{json.dumps(arguments, sort_keys=True, ensure_ascii=False)}"


@dataclass
class FileAssistant:
    config: LlmConfig
    registry: ToolRegistry = field(default_factory=ToolRegistry)
    executor: ToolExecutor = field(default_factory=ToolExecutor)
    tracker: UsageTracker = field(default_factory=UsageTracker)
    messages: list[dict[str, Any]] = field(
        default_factory=lambda: [{"role": "system", "content": SYSTEM_PROMPT}]
    )

    def run(self, prompt: str) -> AgentResult:
        self.messages.append({"role": "user", "content": prompt})
        tools = self.registry.openai_tools()
        tool_calls_count = 0
        last_signature = ""
        repeat_count = 0

        for round_no in range(1, TOOL_LOOP_FUSE + 1):
            message, _usage = complete(
                self.config,
                self.messages,
                tools=tools,
                tracker=self.tracker,
            )
            tool_calls = message.get("tool_calls") or []
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
                    if not isinstance(arguments, dict):
                        arguments = {}

                    signature = _signature(name, arguments)
                    if signature == last_signature:
                        repeat_count += 1
                    else:
                        last_signature = signature
                        repeat_count = 1

                    if repeat_count >= MAX_REPEAT_SAME_TOOL:
                        content = (
                            f"Stopped due to repeated tool call: {name} "
                            f"with the same arguments {repeat_count} times."
                        )
                        self.messages.append({"role": "assistant", "content": content})
                        return AgentResult(content, tool_calls_count, self.tracker)

                    rendered_args = json.dumps(arguments, ensure_ascii=False)
                    print(f"[tool] round={round_no} {name}({rendered_args})")
                    try:
                        result = self.executor.call(name, arguments)
                    except Exception as exc:  # noqa: BLE001
                        result = json.dumps({"error": str(exc)}, ensure_ascii=False)
                    tool_calls_count += 1
                    preview = result if len(result) <= 220 else result[:220] + "..."
                    print(f"[tool] result {preview}")
                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id") or name,
                            "content": result,
                        }
                    )
                continue

            content = (message.get("content") or "").strip()
            self.messages.append({"role": "assistant", "content": content})
            return AgentResult(content, tool_calls_count, self.tracker)

        content = f"Stopped after {TOOL_LOOP_FUSE} rounds without a final answer."
        self.messages.append({"role": "assistant", "content": content})
        return AgentResult(content, tool_calls_count, self.tracker)
