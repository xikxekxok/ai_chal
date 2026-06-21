"""LLM-классификатор: память + user-driven FSM TikTok-съёмки."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from llm import LlmConfig, UsageTracker, complete
from memory import MemoryStore
from profiles import ProfileStore
from task_state import (
    FIELD_LABELS,
    STAGE_REQUIRED_FIELDS,
    apply_fsm_event,
)

CLASSIFIER_SYSTEM = """\
Ты — служебный **классификатор** (JSON API) для бэкенда приюта opossumов «Хvostik».
Ты **НЕ** ассистент смены. **НЕ** отвечай пользователю — только машинный JSON.

Анализируй **только сообщение ПОЛЬЗОВАТЕЛЯ** (и контекст FSM):
1) новые факты для памяти (saves);
2) событие FSM.

Текст «Ассистент: …» — контекст диалога, **не** источник переходов FSM.

## Память (saves)

Слои: **long** (устав, правила), **working** (факты о opossume). profile не используй.

## FSM — переходы делает ПОЛЬЗОВАТЕЛЬ

Стадии: pitch → welfare_check → rehearsal → publish → done

Поля stage_data по этапам (ключ → смысл):
- pitch: story, participants, duration
- welfare_check: balloon_ok, tether_ok, stress_ok
- rehearsal: dry_run_done
- publish: final_ready

### update_step

Если пользователь **сообщил факты** текущего этапа — заполни stage_data.
Пример: «сюжет — Тофик на шаре, я бегу, 15 сек, участники я и Тофик» →
{"event":"update_step","stage_data":{"story":"...","participants":"...","duration":"15 сек"}}

### complete_stage

Если пользователь **явно закрывает этап**: «бриф готов», «можем идти дальше»,
«переходим», «этап закрыт» — **complete_stage**.

**Важно:** в том же JSON добавь **stage_data** с фактами из последней реплики
и из недавнего диалога, если их ещё нет в FSM. Код сначала запишет факты,
потом проверит переход.

Пример:
{"event":"complete_stage","stage_data":{"story":"...","participants":"...","duration":"15 сек"}}

### advance

Только если пользователь **пытается перепрыгнуть** этап («сразу publish», «выложим без welfare»).
Код отклонит недопустимый skip.

### pause / resume / null

Верни ТОЛЬКО JSON:
{"saves": [...], "fsm": {...}} или {"saves": [], "fsm": null}
"""


@dataclass
class ClassifierResult:
    saves: list[dict[str, Any]]
    raw: str
    applied: list[str]
    profile_applied: list[str]
    fsm_applied: list[str]
    skipped: bool
    fsm: dict[str, Any] | None = field(default=None)


def _format_dialog_for_classifier(memory: MemoryStore, user: str) -> str:
    lines: list[str] = []
    for msg in memory.short.recent(8):
        role = "Пользователь" if msg["role"] == "user" else "Ассистент"
        lines.append(f"{role}: {msg['content']}")
    lines.append(f"Пользователь: {user}")
    lines.append("(классифицируй последнюю реплику «Пользователь:»)")
    return "\n".join(lines)


def _required_fields_hint(stage_value: str) -> str:
    from task_state import parse_stage

    stage = parse_stage(stage_value)
    if stage is None:
        return ""
    keys = STAGE_REQUIRED_FIELDS.get(stage, ())
    if not keys:
        return ""
    return ", ".join(f"{k} ({FIELD_LABELS.get(k, k)})" for k in keys)


def _parse_classifier_json(content: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return [], None
    if not isinstance(parsed, dict):
        return [], None
    saves = parsed.get("saves")
    if not isinstance(saves, list):
        saves = []
    saves = [s for s in saves if isinstance(s, dict)]
    fsm = parsed.get("fsm")
    if fsm is not None and not isinstance(fsm, dict):
        fsm = None
    if isinstance(fsm, dict):
        event = fsm.get("event")
        if event is None or str(event).lower() in ("null", "none", ""):
            fsm = None
    return saves, fsm


def classify_user_input(
    config: LlmConfig,
    memory: MemoryStore,
    profiles: ProfileStore,
    task_state,
    profile_id: str,
    user: str,
    *,
    tracker: UsageTracker | None = None,
    skip_profile_updates: bool = False,
) -> ClassifierResult:
    """Классификация реплики пользователя **до** ответа агента (FSM, память)."""
    profile = profiles.get(profile_id)
    profile_block = profiles.to_prompt_block(profile) if profile else "(нет профиля)"
    dialog = _format_dialog_for_classifier(memory, user)
    fsm_block = task_state.to_prompt_block()
    stage_value = task_state.state.stage.value if task_state.state else "?"
    fields_hint = _required_fields_hint(stage_value)
    user_content = (
        f"Активный профиль: {profile_id}\n{profile_block}\n\n"
        f"FSM:\n{fsm_block}\n\n"
        f"Поля текущего этапа ({stage_value}): {fields_hint or '(нет)'}\n\n"
        f"Текущее состояние памяти:\n{memory.context_summary()}\n\n"
        f"Диалог:\n{dialog}\n\n"
        "Классифицируй последнюю реплику пользователя. Верни только JSON saves + fsm."
    )
    messages = [
        {"role": "system", "content": CLASSIFIER_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    raw, _ = complete(config, messages, tracker=tracker)
    saves, fsm = _parse_classifier_json(raw)

    applied: list[str] = []
    profile_applied: list[str] = []
    for item in saves:
        layer = str(item.get("layer", "")).strip().lower()
        if layer == "profile":
            if skip_profile_updates:
                continue
            updates = item.get("updates")
            if isinstance(updates, dict):
                changed = profiles.apply_update(profile_id, updates)
                for detail in changed:
                    profile_applied.append(f"{profile_id}: +{detail}")
            continue
        result = memory.apply_save(item)
        if result is not None:
            applied.append(f"{result.layer}: {result.detail}")

    fsm_applied = apply_fsm_event(task_state, fsm, profile_id)

    skipped = not applied and not profile_applied and not fsm_applied
    return ClassifierResult(
        saves=saves,
        raw=raw,
        applied=applied,
        profile_applied=profile_applied,
        fsm_applied=fsm_applied,
        skipped=skipped,
        fsm=fsm,
    )
