"""LLM-классификатор: память + события FSM."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from llm import LlmConfig, UsageTracker, complete
from memory import MemoryStore
from profiles import ProfileStore
from task_state import Stage, apply_fsm_event

CLASSIFIER_SYSTEM = """\
Ты классификатор памяти и FSM ассистента ночного приюта опossumов «Хvостik».

После каждого хода реши:
1) какие НОВЫЕ факты из сообщения ПОЛЬЗОВАТЕЛЯ сохранить в память;
2) нужно ли событие FSM (управление заявкой на выдачу).

Главный источник — реплика пользователя; ответ ассистента — только для контекста.

## Память (saves)

Слои (whitelist — только эти три):
1. **long** — правила приюта: часы, карантин, устав.
   {"layer": "long", "patch": "текст"}
2. **working** — факты о конкретном опossume.
   {"layer": "working", "opossum": "Имя", "facts": {"ключ": "значение"}}
3. **profile** — явные предпочтения стиля («запомни», «всегда», «фиксируй»).
   {"layer": "profile", "updates": {"learned": {"ключ": "значение"}}}

## FSM (fsm)

Типы exit-документов по этапам:
- application_review → adoption_application (анкета одобрена)
- home_visit → home_visit_act (акт визита)
- trial_period → trial_period_report (отчёт о пробном периоде)
- vet_clearance → vet_examination_protocol (протокол осмотра)
- contract → adoption_contract (договор подписан)

События fsm.event:
- **update_step** — новые факты этапа, stage_data, без нового документа
- **add_artifact** — пользователь фиксирует документ
  (анкета одобрена, визит прошёл, осмотр, договор)
- **advance** — явный переход (обычно после add_artifact; можно null если документ уже добавлен)
- **pause** — «на сегодня хватит», «продолжим завтра»
- **resume** — «продолжаем», «чего там с Оскаром», «как дела с выдачей» после паузы
- **null** — болтовня, вопросы без изменения процесса

add_artifact пример:
{"event": "add_artifact", "artifact": {
  "type": "adoption_application",
  "title": "Анкета семьи Ивановых",
  "summary": "Условия содержания соответствуют уставу.",
  "status": "approved",
  "by": "martha"
}}

НЕ вызывай advance если пользователь просит перескочить этап (сразу договор без визита) — fsm: null.
НЕ меняй applicant в FSM. Смена семьи — fsm: null.
НЕ сохраняй working-факты о смене семьи или переоформлении на других заявителей.

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


def _format_recent_dialog(memory: MemoryStore, user: str, assistant: str) -> str:
    lines: list[str] = []
    for msg in memory.short.recent(6):
        role = "Пользователь" if msg["role"] == "user" else "Ассистент"
        lines.append(f"{role}: {msg['content']}")
    lines.append(f"Пользователь: {user}")
    lines.append(f"Ассистент: {assistant}")
    return "\n".join(lines)


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


def _fsm_heuristic(user: str, stage: Stage | None) -> dict[str, Any] | None:
    text = user.lower()
    if not text:
        return None

    pause_patterns = [
        r"продолжим завтра",
        r"на сегодня (?:хватит|всё|все|можно)",
        r"завтра продолж",
        r"на сегодня законч",
        r"смена подходит к концу",
        r"на сегодня выдохнуть",
        r"на сегодня можно",
    ]
    for pat in pause_patterns:
        if re.search(pat, text):
            return {"event": "pause"}

    resume_patterns = [
        r"чего там с оскар",
        r"как там (?:наш|у нас) оскар",
        r"как дела с (?:оскар|выдач)",
        r"ну чего там",
        r"продолжаем",
        r"где мы останов",
    ]
    for pat in resume_patterns:
        if re.search(pat, text):
            return {"event": "resume"}

    if stage == Stage.APPLICATION_REVIEW and re.search(
        r"анкет.*(?:одобр|в порядке|ок|готов)|(?:можно|двига).*регламент", text
    ):
        return {
            "event": "add_artifact",
            "artifact": {
                "type": "adoption_application",
                "title": "Анкета семьи Ивановых",
                "summary": "Условия содержания соответствуют уставу.",
                "status": "approved",
                "by": "martha",
            },
        }

    if stage == Stage.HOME_VISIT and re.search(
        r"(?:визит|осмотр).*?(?:состоял|прош|норм|зафиксир|акт)", text
    ):
        return {
            "event": "add_artifact",
            "artifact": {
                "type": "home_visit_act",
                "title": "Акт домашнего визита семьи Ивановых",
                "summary": "Условия содержания на месте соответствуют требованиям.",
                "status": "filed",
                "by": "martha",
            },
        }

    if stage == Stage.TRIAL_PERIOD and re.search(
        r"(?:пробн|недел).*(?:без проблем|справля|успеш|норм|прош)", text
    ):
        return {
            "event": "add_artifact",
            "artifact": {
                "type": "trial_period_report",
                "title": "Отчёт о пробном периоде",
                "summary": "Семья Ивановых справляется, инцидентов нет.",
                "status": "filed",
                "by": "martha",
            },
        }

    if stage == Stage.VET_CLEARANCE and re.search(
        r"(?:клык|вет|осмотр).*(?:чист|clear|готов|можно к договор|всё ок)", text
    ):
        return {
            "event": "add_artifact",
            "artifact": {
                "type": "vet_examination_protocol",
                "title": "Протокол осмотра Оскара",
                "summary": "Осмотр пройден, противопоказаний к выдаче нет.",
                "status": "approved",
                "by": "klyk",
            },
        }

    if stage == Stage.CONTRACT and re.search(
        r"(?:договор|контракт).*(?:подпис|заключ|официальн)", text
    ):
        return {
            "event": "add_artifact",
            "artifact": {
                "type": "adoption_contract",
                "title": "Договор об усыновлении Оскара",
                "summary": "Договор с семьёй Ивановых подписан.",
                "status": "signed",
                "by": "martha",
            },
        }

    return None


def classify_turn(
    config: LlmConfig,
    memory: MemoryStore,
    profiles: ProfileStore,
    task_state,
    profile_id: str,
    user: str,
    assistant: str,
    *,
    tracker: UsageTracker | None = None,
) -> ClassifierResult:
    profile = profiles.get(profile_id)
    profile_block = profiles.to_prompt_block(profile) if profile else "(нет профиля)"
    dialog = _format_recent_dialog(memory, user, assistant)
    fsm_block = task_state.to_prompt_block()
    user_content = (
        f"Активный профиль: {profile_id}\n{profile_block}\n\n"
        f"FSM:\n{fsm_block}\n\n"
        f"Текущее состояние памяти:\n{memory.context_summary()}\n\n"
        f"Последний ход:\n{dialog}\n\n"
        "Верни JSON saves + fsm."
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

    current_stage = task_state.state.stage if task_state.state else None
    if fsm is None:
        fsm = _fsm_heuristic(user, current_stage)

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
