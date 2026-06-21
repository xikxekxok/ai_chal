"""LLM-классификатор: куда сохранить факты из хода диалога."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from llm import LlmConfig, UsageTracker, complete
from memory import MemoryStore
from profiles import ProfileStore

CLASSIFIER_SYSTEM = """\
Ты классификатор памяти ассистента ночного приюта опossumов «Хvостik».

После каждого хода реши, какие НОВЫЕ факты из сообщения ПОЛЬЗОВАТЕЛЯ сохранить.
Главный источник — реплика пользователя; ответ ассистента — только для контекста.

Слои (whitelist — только эти три):
1. **long** — правила приюта: часы смены, карантин, выдача, устав, регламент.
   {"layer": "long", "patch": "текст для устава"}
2. **working** — факты о конкретном опossume: имя, вес, симптомы, карантин, еда, поведение.
   {"layer": "working", "opossum": "Имя", "facts": {"ключ": "значение"}}
3. **profile** — явные предпочтения собеседника о стиле/формате/ограничениях ответов.
   {"layer": "profile", "updates": {"learned": {"ключ": "значение"}}}
   Сохраняй profile только если пользователь явно просит запомнить предпочтение
   («запомни», «всегда», «мне удобнее», «фиксируй», «отчёты только…»).
   Не дублируй то, что уже есть в seed-профиле.

НЕ сохраняй: болтовню, погоду, усталость, эмоции без новых фактов.
Сохраняй каждый новый факт о опossume (вес, симптом, карантин, аппетит) — отдельной записью working.

Верни ТОЛЬКО JSON: {"saves": [...]} или {"saves": []}.
"""


@dataclass
class ClassifierResult:
    saves: list[dict[str, Any]]
    raw: str
    applied: list[str]
    profile_applied: list[str]
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


def _profile_heuristic(user: str) -> dict[str, str] | None:
    text = user.strip()
    if not text:
        return None
    patterns = [
        (re.compile(r"запомни[:\s—-]+(.+)", re.I | re.DOTALL), "ночной_формат"),
        (re.compile(r"всегда указывай (.+)", re.I | re.DOTALL), "дозировки"),
        (re.compile(r"фиксируй[:\s—-]+(.+)", re.I | re.DOTALL), "формат_отчётов"),
    ]
    for pattern, key in patterns:
        match = pattern.search(text)
        if match:
            value = match.group(1).strip().rstrip(".")
            if value:
                return {key: value}
    return None


def classify_turn(
    config: LlmConfig,
    memory: MemoryStore,
    profiles: ProfileStore,
    profile_id: str,
    user: str,
    assistant: str,
    *,
    tracker: UsageTracker | None = None,
) -> ClassifierResult:
    profile = profiles.get(profile_id)
    profile_block = profiles.to_prompt_block(profile) if profile else "(нет профиля)"
    dialog = _format_recent_dialog(memory, user, assistant)
    user_content = (
        f"Активный профиль: {profile_id}\n{profile_block}\n\n"
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
    profile_applied: list[str] = []
    for item in saves:
        layer = str(item.get("layer", "")).strip().lower()
        if layer == "profile":
            updates = item.get("updates")
            if isinstance(updates, dict):
                changed = profiles.apply_update(profile_id, updates)
                for detail in changed:
                    profile_applied.append(f"{profile_id}: +{detail}")
            continue
        result = memory.apply_save(item)
        if result is not None:
            applied.append(f"{result.layer}: {result.detail}")
    if not profile_applied:
        heuristic = _profile_heuristic(user)
        if heuristic:
            changed = profiles.apply_update(profile_id, {"learned": heuristic})
            for detail in changed:
                profile_applied.append(f"{profile_id}: +{detail}")
    return ClassifierResult(
        saves=saves,
        raw=raw,
        applied=applied,
        profile_applied=profile_applied,
        skipped=not applied and not profile_applied,
    )
