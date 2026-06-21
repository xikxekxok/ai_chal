"""LLM-классификатор: куда сохранить факты из хода диалога."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from llm import LlmConfig, UsageTracker, complete
from memory import MemoryStore

CLASSIFIER_SYSTEM = """\
Ты классификатор памяти ассистента ночного приюта опossumов «Хvостik».

После каждого хода реши, какие НОВЫЕ факты из сообщения ПОЛЬЗОВАТЕЛЯ сохранить.
Главный источник — реплика пользователя; ответ ассистента — только для контекста.

Слои (whitelist — только эти два):
1. **long** — правила приюта: часы смены, карантин, выдача, устав, регламент.
   {"layer": "long", "patch": "текст для устава"}
2. **working** — факты о конкретном опossume: имя, вес, симптомы, карантин, еда, поведение.
   {"layer": "working", "opossum": "Имя", "facts": {"ключ": "значение"}}

НЕ сохраняй: болтовню, погоду, усталость, эмоции без новых фактов.
Сохраняй каждый новый факт о опossume (вес, симптом, карантин, аппетит) — отдельной записью working.

Верни ТОЛЬКО JSON: {"saves": [...]} или {"saves": []}.
"""


@dataclass
class ClassifierResult:
    saves: list[dict[str, Any]]
    raw: str
    applied: list[str]
    skipped: bool


def _format_recent_dialog(memory: MemoryStore, user: str, assistant: str) -> str:
    lines: list[str] = []
    for msg in memory.short.recent(6):
        role = "Пользователь" if msg["role"] == "user" else "Ассистент"
        lines.append(f"{role}: {msg['content']}")
    lines.append(f"Пользователь: {user}")
    lines.append(f"Ассистент: {assistant}")
    return "\n".join(lines)


def _parse_saves(content: str) -> list[dict[str, Any]]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, dict):
        return []
    saves = parsed.get("saves")
    if not isinstance(saves, list):
        return []
    return [s for s in saves if isinstance(s, dict)]


def classify_turn(
    config: LlmConfig,
    memory: MemoryStore,
    user: str,
    assistant: str,
    *,
    tracker: UsageTracker | None = None,
) -> ClassifierResult:
    dialog = _format_recent_dialog(memory, user, assistant)
    user_content = (
        f"Текущее состояние памяти:\n{memory.context_summary()}\n\n"
        f"Последний ход:\n{dialog}\n\n"
        "Верни JSON saves."
    )
    messages = [
        {"role": "system", "content": CLASSIFIER_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    raw, _ = complete(config, messages, tracker=tracker)
    saves = _parse_saves(raw)
    applied: list[str] = []
    for item in saves:
        result = memory.apply_save(item)
        if result is not None:
            applied.append(f"{result.layer}: {result.detail}")
    return ClassifierResult(
        saves=saves,
        raw=raw,
        applied=applied,
        skipped=not applied,
    )
