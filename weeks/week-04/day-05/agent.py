"""Шерлок Хвостсон — агент-сыщик с MCP tool-loop."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from console_out import print_mcp, print_tagged
from llm import LlmConfig, UsageTracker, complete_message
from mcp_client import McpToolClient
from narration import format_mcp_call, reveal_tool_result

MAX_REPEAT_SAME_TOOL = 3

SYSTEM_PROMPT = """\
Ты — Шерлок Хвостсон, сыщик Opossum Borough. Собеседник — Доктор Ватсон-опоссум.
Дело missing_ball (14 мая 2024, приют к югу от Подольска): пропал фитбол **Тофика**
для ролика «Тофик на шаре».

Инструменты:
- burrow: list_case_files, read_case_file, list_suspects — архив;
- trail: web_search, read_page — внешние проверки (факты, справочные данные);
- snout: add_clue, list_clues, test_theory, build_timeline, accuse — дедукция.

**Перед каждым tool** — 1–2 предложения: что делаешь и зачем (цепочка рассуждений).

Алгоритм:
1. list_case_files, затем read_case_file для каждого id: yard_report, witness_marta,
   gazebo_log, shed_findings, suspects.
2. Зафиксируй улики с тегами (массив строк, не JSON-строка).
3. Сверь противоречивые версии через trail, если нужно (например, физика vs ворона).
4. test_theory по подозреваемым; accuse только при **supported**.

Полезные теги: witness_marta, near_bushes, dozent_alibi_broken, shed_traces,
fiber_theater, weather_confirmed, crow_too_heavy, sasha_alibi, barbos_chained,
time:18:35, time:18:38, time:18:40, time:18:45.

[заметка сыщика, не озвучивать: сверяй алиби с журналом и осмотром; внешние
факты (метео, физика) — через trail; accuse только при supported.]

Финал: драматичное объяснение + «Элементарно, Ватсон». Факты — только из tools.
По-русски.
"""


@dataclass
class TurnResult:
    reply: str
    prompt_tokens: int
    completion_tokens: int
    accused: str | None = None


def _tool_signature(name: str, arguments: dict[str, Any]) -> str:
    return f"{name}:{json.dumps(arguments, sort_keys=True, ensure_ascii=False)}"


def _parse_payload(tool_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(tool_text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _print_holmes_thought(text: str) -> None:
    text = text.strip()
    if not text:
        return
    print_tagged("holmes", text)


@dataclass
class HolmesAgent:
    config: LlmConfig
    mcp: McpToolClient
    tracker: UsageTracker
    messages: list[dict[str, Any]]
    last_accused: str | None = None

    @classmethod
    def create(cls, config: LlmConfig, mcp: McpToolClient) -> HolmesAgent:
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
        print_tagged("holmes", f"{reason} — формулирую итог без tools.")
        message, _ = complete_message(
            self.config,
            self.messages,
            tracker=self.tracker,
        )
        content = message.get("content") or (
            "Не удалось завершить расследование: слишком много вызовов tools."
        )
        self.messages.append({"role": "assistant", "content": content})
        prompt_delta, completion_delta = self._turn_usage_delta(usage_before)
        return TurnResult(
            reply=content,
            prompt_tokens=prompt_delta,
            completion_tokens=completion_delta,
            accused=self.last_accused,
        )

    async def run_turn(self, user_input: str) -> TurnResult:
        self.messages.append({"role": "user", "content": user_input})
        tools = self.mcp.llm_tools()
        usage_before = (self.tracker.prompt_tokens, self.tracker.completion_tokens)
        last_signature = ""
        repeat_count = 0

        while True:
            message, _ = complete_message(
                self.config,
                self.messages,
                tools=tools,
                tracker=self.tracker,
            )
            tool_calls = message.get("tool_calls")
            if tool_calls:
                thought = str(message.get("content") or "").strip()
                _print_holmes_thought(thought)
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

                    server = self.mcp.server_for(name)
                    call_label = format_mcp_call(name, arguments)
                    print_mcp(server, call_label)

                    tool_text = await self.mcp.call_tool(name, arguments)
                    payload = _parse_payload(tool_text)
                    if name == "accuse" and payload.get("ok"):
                        self.last_accused = str(payload.get("suspect_name") or "")

                    reveal_tool_result(server, name, payload, arguments=arguments)
                    if isinstance(payload, dict) and "error" in payload:
                        print_tagged("error", f"{name}: {payload['error']}")

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
                accused=self.last_accused,
            )
