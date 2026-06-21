"""Ассистент смены приюта «Хvостik» с тремя слоями памяти."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from classifier import ClassifierResult, classify_turn
from llm import LlmConfig, UsageTracker, complete
from memory import MemoryStore

DEFAULT_SYSTEM = """\
Ты — операционный ассистент ночной смены приюта для опossumов «Хvостik».
Собеседник — смотритель или директор.
Отвечай по-русски, по делу, с лёгким opossum-юмором где уместно.

Используй:
- **Устав приюта** (долговременная память) — для правил, часов, карантина, выдачи.
- **Карточки опossumов** (рабочая память) — для фактов о подопечных.
- **Историю текущего диалога** — для контекста беседы.

Если спрашивают «что зафиксировано» по опossumу — опирайся на рабочую память, не выдумывай.
Если спрашивают про правила — цитируй устав.
Если директор просит зафиксировать изменение устава (часы, регламент) —
подтверди и опирайся на long.
Ты не HR-отдел, но изменения **устава приюта** — твоя зона (долговременная память).
"""


@dataclass
class TurnResult:
    reply: str
    classifier: ClassifierResult
    prompt_tokens: int
    completion_tokens: int


@dataclass
class ShelterAgent:
    config: LlmConfig
    memory: MemoryStore
    tracker: UsageTracker
    system_prompt: str = DEFAULT_SYSTEM

    def build_messages(self, user_input: str) -> list[dict[str, str]]:
        system = (
            f"{self.system_prompt}\n\n"
            f"## Устав приюта (long)\n{self.memory.long.to_prompt_block()}\n\n"
            f"## Карточки опossumов (working)\n{self.memory.working.to_prompt_block()}"
        )
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        for msg in self.memory.short.messages:
            role = msg["role"]
            if role in ("user", "assistant"):
                messages.append({"role": role, "content": msg["content"]})
        messages.append({"role": "user", "content": user_input})
        return messages

    def run_turn(self, user_input: str) -> TurnResult:
        messages = self.build_messages(user_input)
        reply, usage = complete(self.config, messages, tracker=self.tracker)
        self.memory.short.add_turn(user_input, reply)
        self.memory.short.save()
        classifier = classify_turn(
            self.config,
            self.memory,
            user_input,
            reply,
            tracker=self.tracker,
        )
        return TurnResult(
            reply=reply,
            classifier=classifier,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
        )


def create_agent(data_dir: Path, config: LlmConfig) -> ShelterAgent:
    memory = MemoryStore(data_dir)
    memory.load()
    return ShelterAgent(config=config, memory=memory, tracker=UsageTracker())
