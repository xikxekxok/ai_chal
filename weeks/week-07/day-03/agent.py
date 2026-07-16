from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from llm import LlmConfig, complete_message
from mcp_client import McpClient, preview_json
from rag import KnowledgeDoc, search_kb

TOOL_LOOP_FUSE = 8

SYSTEM_PROMPT = """\
Ты саппорт-ассистент NoteSync.
Отвечай только по-русски, кратко и по делу.
У тебя есть локальная база знаний и CRM с пользователями и тикетами.
Перед ответом используй tools, если вопрос связан с политиками, багами, авторизацией,
тикетом или пользователем. Не выдумывай факты вне найденного контекста.
В финальном ответе:
1. Кратко объясни вероятную причину.
2. Укажи, на что опираешься: KB, тикет, пользователь.
3. Предложи 2-4 следующих шага поддержки.
Если уже достаточно контекста из KB или CRM, перестань вызывать tools и дай ответ.
"""


def build_search_tool_schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "search_kb",
            "description": "Search local markdown knowledge base by keywords.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 5},
                },
                "required": ["query"],
            },
        },
    }


@dataclass
class AgentResult:
    reply: str
    prompt_tokens: int
    completion_tokens: int


class SupportAgent:
    def __init__(self, config: LlmConfig, kb_docs: list[KnowledgeDoc], mcp: McpClient) -> None:
        self._config = config
        self._kb_docs = kb_docs
        self._mcp = mcp
        self._messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.prompt_tokens = 0
        self.completion_tokens = 0

    async def run(self, user_prompt: str) -> AgentResult:
        self._messages.append({"role": "user", "content": user_prompt})
        tools = [build_search_tool_schema(), *self._mcp.llm_tools()]
        before_prompt = self.prompt_tokens
        before_completion = self.completion_tokens
        last_signature = ""
        repeat_count = 0

        for round_no in range(1, TOOL_LOOP_FUSE + 1):
            message, usage = complete_message(self._config, self._messages, tools=tools)
            self.prompt_tokens += usage["prompt_tokens"]
            self.completion_tokens += usage["completion_tokens"]
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                content = message.get("content") or ""
                self._messages.append({"role": "assistant", "content": content})
                return AgentResult(
                    reply=content,
                    prompt_tokens=self.prompt_tokens - before_prompt,
                    completion_tokens=self.completion_tokens - before_completion,
                )

            self._messages.append(message)
            for call in tool_calls:
                fn = call.get("function") or {}
                name = fn.get("name") or ""
                raw_arguments = fn.get("arguments") or "{}"
                try:
                    arguments = json.loads(raw_arguments)
                except json.JSONDecodeError:
                    arguments = {}
                signature = f"{name}:{json.dumps(arguments, sort_keys=True, ensure_ascii=False)}"
                if signature == last_signature:
                    repeat_count += 1
                else:
                    last_signature = signature
                    repeat_count = 1
                if repeat_count >= 3:
                    return self._final_answer(
                        before_prompt,
                        before_completion,
                        "Контекста уже достаточно. Дай финальный ответ без новых tools.",
                    )
                print(f"[tool] round {round_no} -> {name}({preview_json(arguments)})", flush=True)
                if name == "search_kb":
                    result = search_kb(
                        str(arguments.get("query") or ""),
                        self._kb_docs,
                        limit=int(arguments.get("limit") or 3),
                    )
                    print(
                        f"[retrieve] kb hits={result['count']} query={result['query']!r}",
                        flush=True,
                    )
                    tool_text = json.dumps(result, ensure_ascii=False)
                else:
                    tool_text = await self._mcp.call_tool(name, arguments)
                    print(f"[tool] {name} -> {preview_json(tool_text)}", flush=True)
                self._messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id") or "",
                        "content": tool_text,
                    }
                )

        return self._final_answer(
            before_prompt,
            before_completion,
            "Лимит tool-loop достигнут. Сформируй лучший возможный ответ без новых tools.",
        )

    def _final_answer(
        self,
        before_prompt: int,
        before_completion: int,
        instruction: str,
    ) -> AgentResult:
        self._messages.append({"role": "system", "content": instruction})
        message, usage = complete_message(self._config, self._messages, tools=None)
        self.prompt_tokens += usage["prompt_tokens"]
        self.completion_tokens += usage["completion_tokens"]
        content = message.get("content") or ""
        self._messages.append({"role": "assistant", "content": content})
        return AgentResult(
            reply=content,
            prompt_tokens=self.prompt_tokens - before_prompt,
            completion_tokens=self.completion_tokens - before_completion,
        )
