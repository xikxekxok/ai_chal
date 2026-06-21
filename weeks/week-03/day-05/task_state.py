"""FSM съёмки TikTok «Хvostik Clips» — переходы от пользователя, агент ограничен этапом."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

VALID_ARTIFACT_STATUSES = frozenset({"draft", "approved", "signed", "filed"})

TIKTOK_CASE_FILE = "tiktok_shoot.json"


class Stage(StrEnum):
    PITCH = "pitch"
    WELFARE_CHECK = "welfare_check"
    REHEARSAL = "rehearsal"
    PUBLISH = "publish"
    DONE = "done"


STAGE_ORDER: list[Stage] = [
    Stage.PITCH,
    Stage.WELFARE_CHECK,
    Stage.REHEARSAL,
    Stage.PUBLISH,
    Stage.DONE,
]

ALLOWED_TRANSITIONS: dict[Stage, frozenset[Stage]] = {
    Stage.PITCH: frozenset({Stage.WELFARE_CHECK}),
    Stage.WELFARE_CHECK: frozenset({Stage.REHEARSAL}),
    Stage.REHEARSAL: frozenset({Stage.PUBLISH}),
    Stage.PUBLISH: frozenset({Stage.DONE}),
    Stage.DONE: frozenset(),
}

STAGE_EXIT_ARTIFACTS: dict[Stage, str] = {
    Stage.PITCH: "pitch_brief",
    Stage.WELFARE_CHECK: "welfare_clearance",
    Stage.REHEARSAL: "rehearsal_take",
    Stage.PUBLISH: "publish_ticket",
}

# Поля stage_data, которые волонтёр должен сообщить до complete_stage.
STAGE_REQUIRED_FIELDS: dict[Stage, tuple[str, ...]] = {
    Stage.PITCH: ("story", "participants", "duration"),
    Stage.WELFARE_CHECK: ("balloon_ok", "tether_ok", "stress_ok"),
    Stage.REHEARSAL: ("dry_run_done",),
    Stage.PUBLISH: ("final_ready",),
}

FIELD_LABELS: dict[str, str] = {
    "story": "сюжет",
    "participants": "участники",
    "duration": "длительность",
    "balloon_ok": "высота шара / безопасность",
    "tether_ok": "страховочная привязь",
    "stress_ok": "стресс подопечного",
    "dry_run_done": "пробный дубль снят",
    "final_ready": "финальный ролик готов",
}

STAGE_DEFAULTS: dict[Stage, dict[str, str]] = {
    Stage.PITCH: {
        "step": "Согласовать идею ролика",
        "expected_action": "Волонтёр: описать сюжет, длительность, участников",
    },
    Stage.WELFARE_CHECK: {
        "step": "Проверка благополучия подопечного",
        "expected_action": "Волонтёр: подтвердить безопасность шара, привязь, стресс",
    },
    Stage.REHEARSAL: {
        "step": "Пробный дубль",
        "expected_action": "Волонтёр: снять черновик без публикации",
    },
    Stage.PUBLISH: {
        "step": "Одобрение публикации",
        "expected_action": "Волонтёр: финальный монтаж и выкладка",
    },
    Stage.DONE: {
        "step": "Ролик в очереди",
        "expected_action": "Кейс закрыт",
    },
}

STAGE_LABELS: dict[Stage, str] = {
    Stage.PITCH: "бриф идеи",
    Stage.WELFARE_CHECK: "благополучие",
    Stage.REHEARSAL: "репетиция",
    Stage.PUBLISH: "публикация",
    Stage.DONE: "завершено",
}

ARTIFACT_LABELS: dict[str, str] = {
    "pitch_brief": "Бриф идеи ролика",
    "welfare_clearance": "Допуск по благополучию",
    "rehearsal_take": "Одобренный пробный дубль",
    "publish_ticket": "Тикет на публикацию",
}

# Темы, которых агент не должен касаться на данном этапе.
STAGE_AGENT_FORBIDDEN: dict[Stage, str] = {
    Stage.PITCH: "инструкции по съёмке, welfare, репетиция, монтаж, публикация, «выложи в TikTok»",
    Stage.WELFARE_CHECK: "съёмка дубля, репетиция, монтаж, публикация, «выложи в TikTok»",
    Stage.REHEARSAL: "финальный монтаж, публикация, «выложи в TikTok»",
    Stage.PUBLISH: "(нет — можно обсуждать выкладку)",
    Stage.DONE: "(кейс закрыт)",
}


def can_transition(from_stage: Stage, to_stage: Stage) -> tuple[bool, str]:
    allowed = ALLOWED_TRANSITIONS.get(from_stage, frozenset())
    if to_stage not in allowed:
        opts = ", ".join(s.value for s in sorted(allowed, key=lambda x: STAGE_ORDER.index(x)))
        return False, (
            f"{from_stage.value} → {to_stage.value} запрещён"
            + (f" (допустимо: {opts})" if opts else "")
        )
    return True, ""


def next_allowed_stage(stage: Stage) -> Stage | None:
    allowed = ALLOWED_TRANSITIONS.get(stage, frozenset())
    if not allowed:
        return None
    for candidate in STAGE_ORDER:
        if candidate in allowed:
            return candidate
    return next(iter(allowed))


def parse_stage(value: str | None) -> Stage | None:
    if not value:
        return None
    try:
        return Stage(str(value).strip())
    except ValueError:
        return None


def _field_filled(stage_data: dict[str, Any], key: str) -> bool:
    val = stage_data.get(key)
    if val is None:
        return False
    text = str(val).strip().lower()
    if not text or text in ("нет", "false", "0", "—", "-"):
        return False
    return True


def missing_fields(stage: Stage, stage_data: dict[str, Any]) -> list[str]:
    required = STAGE_REQUIRED_FIELDS.get(stage, ())
    return [key for key in required if not _field_filled(stage_data, key)]


def stage_data_complete(stage: Stage, stage_data: dict[str, Any]) -> bool:
    return not missing_fields(stage, stage_data)


@dataclass
class Artifact:
    type: str
    title: str
    summary: str
    stage: Stage
    status: str
    by: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "title": self.title,
            "summary": self.summary,
            "stage": self.stage.value,
            "status": self.status,
            "by": self.by,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Artifact | None:
        stage = parse_stage(str(data.get("stage", "")))
        if stage is None:
            return None
        status = str(data.get("status", "draft"))
        if status not in VALID_ARTIFACT_STATUSES:
            status = "draft"
        return cls(
            type=str(data.get("type", "")).strip(),
            title=str(data.get("title", "")).strip(),
            summary=str(data.get("summary", "")).strip(),
            stage=stage,
            status=status,
            by=str(data.get("by", "")).strip(),
            created_at=str(data.get("created_at", "")).strip(),
        )


@dataclass
class TaskState:
    case_id: str
    opossum: str
    applicant: str
    stage: Stage
    step: str
    expected_action: str
    paused: bool = False
    stage_data: dict[str, Any] = field(default_factory=dict)
    artifacts: list[Artifact] = field(default_factory=list)
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "opossum": self.opossum,
            "applicant": self.applicant,
            "stage": self.stage.value,
            "step": self.step,
            "expected_action": self.expected_action,
            "paused": self.paused,
            "stage_data": self.stage_data,
            "artifacts": [a.to_dict() for a in self.artifacts],
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskState | None:
        stage = parse_stage(str(data.get("stage", "")))
        if stage is None:
            return None
        artifacts: list[Artifact] = []
        raw_artifacts = data.get("artifacts")
        if isinstance(raw_artifacts, list):
            for item in raw_artifacts:
                if isinstance(item, dict):
                    art = Artifact.from_dict(item)
                    if art and art.type:
                        artifacts.append(art)
        stage_data = data.get("stage_data")
        if not isinstance(stage_data, dict):
            stage_data = {}
        return cls(
            case_id=str(data.get("case_id", "")).strip(),
            opossum=str(data.get("opossum", "")).strip(),
            applicant=str(data.get("applicant", "")).strip(),
            stage=stage,
            step=str(data.get("step", "")).strip(),
            expected_action=str(data.get("expected_action", "")).strip(),
            paused=bool(data.get("paused")),
            stage_data=stage_data,
            artifacts=artifacts,
            updated_at=str(data.get("updated_at", "")).strip(),
        )


@dataclass
class TaskStateStore:
    path: Path
    state: TaskState | None = None

    def load(self) -> None:
        if not self.path.exists():
            self.state = None
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self.state = None
            return
        if isinstance(data, dict):
            self.state = TaskState.from_dict(data)
        else:
            self.state = None

    def save(self) -> None:
        if self.state is None:
            if self.path.exists():
                self.path.unlink()
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state.updated_at = datetime.now(UTC).isoformat()
        self.path.write_text(
            json.dumps(self.state.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def clear(self) -> None:
        self.state = None
        if self.path.exists():
            self.path.unlink()

    def init_case(self, opossum: str, applicant: str) -> TaskState:
        defaults = STAGE_DEFAULTS[Stage.PITCH]
        slug = opossum.lower().replace(" ", "-")
        self.state = TaskState(
            case_id=f"tiktok-{slug}",
            opossum=opossum.strip(),
            applicant=applicant.strip(),
            stage=Stage.PITCH,
            step=defaults["step"],
            expected_action=defaults["expected_action"],
            paused=False,
        )
        self.save()
        return self.state

    def missing_fields(self, stage: Stage | None = None) -> list[str]:
        if self.state is None:
            return []
        target = stage or self.state.stage
        return missing_fields(target, self.state.stage_data)

    def stage_ready(self, stage: Stage | None = None) -> bool:
        if self.state is None:
            return False
        target = stage or self.state.stage
        return stage_data_complete(target, self.state.stage_data)

    def add_artifact(
        self,
        doc_type: str,
        title: str,
        summary: str,
        status: str,
        by: str,
        *,
        stage: Stage | None = None,
    ) -> Artifact | None:
        if self.state is None:
            return None
        if status not in VALID_ARTIFACT_STATUSES:
            status = "approved"
        target_stage = stage or self.state.stage
        now = datetime.now(UTC).isoformat()
        for art in self.state.artifacts:
            if art.type == doc_type:
                art.title = title or art.title
                art.summary = summary or art.summary
                art.status = status
                art.by = by or art.by
                art.stage = target_stage
                art.created_at = now
                self.save()
                return art
        artifact = Artifact(
            type=doc_type,
            title=title,
            summary=summary,
            stage=target_stage,
            status=status,
            by=by,
            created_at=now,
        )
        self.state.artifacts.append(artifact)
        self.save()
        return artifact

    def _record_stage_completion(self, stage: Stage, by: str) -> None:
        doc_type = STAGE_EXIT_ARTIFACTS.get(stage)
        if not doc_type or self.state is None:
            return
        parts = [
            f"{FIELD_LABELS.get(k, k)}: {v}"
            for k, v in sorted(self.state.stage_data.items())
        ]
        summary = "; ".join(parts) if parts else stage.value
        self.add_artifact(
            doc_type,
            ARTIFACT_LABELS.get(doc_type, doc_type),
            summary,
            "approved",
            by,
            stage=stage,
        )

    def update_step(
        self,
        step: str | None = None,
        expected_action: str | None = None,
        stage_data: dict[str, Any] | None = None,
    ) -> None:
        if self.state is None:
            return
        if step:
            self.state.step = step
        if expected_action:
            self.state.expected_action = expected_action
        if stage_data:
            self.state.stage_data.update(stage_data)
        self.save()

    def pause(self) -> None:
        if self.state is None:
            return
        self.state.paused = True
        self.save()

    def resume(self) -> None:
        if self.state is None:
            return
        self.state.paused = False
        self.save()

    def request_advance(self, target: Stage | None = None) -> tuple[bool, str]:
        if self.state is None:
            return False, "нет активного кейса"
        current = self.state.stage
        if current == Stage.DONE:
            return False, "кейс уже завершён"
        if target is None:
            target = next_allowed_stage(current)
        if target is None:
            return False, f"нет следующего этапа для {current.value}"
        ok, reason = can_transition(current, target)
        if not ok:
            return False, reason
        missing = self.missing_fields(current)
        if missing:
            labels = ", ".join(FIELD_LABELS.get(k, k) for k in missing)
            return False, f"{current.value} → {target.value}: не хватает: {labels}"
        defaults = STAGE_DEFAULTS[target]
        from_label = current.value
        self._record_stage_completion(current, self.state.applicant)
        self.state.stage = target
        self.state.step = defaults["step"]
        self.state.expected_action = defaults["expected_action"]
        self.state.stage_data = {}
        self.state.paused = False
        self.save()
        return True, f"{from_label} → {target.value}"

    def missing_fields_label(self) -> str | None:
        if self.state is None or self.state.stage == Stage.DONE:
            return None
        missing = self.missing_fields()
        if not missing:
            return None
        labels = ", ".join(FIELD_LABELS.get(k, k) for k in missing)
        return labels

    def to_prompt_block(self) -> str:
        if self.state is None:
            return "(активной съёмки TikTok нет)"
        s = self.state
        status = "ПАУЗА" if s.paused else "в работе"
        nxt = next_allowed_stage(s.stage)
        lines = [
            f"Кейс TikTok: **{s.opossum}** — {s.applicant}",
            f"Этап: {s.stage.value} ({STAGE_LABELS.get(s.stage, s.stage.value)})",
            f"Шаг: {s.step}",
            f"Ожидается: {s.expected_action}",
            f"Статус: {status}",
        ]
        if nxt and s.stage != Stage.DONE:
            lines.append(f"Следующий допустимый этап: {nxt.value}")
        forbidden = STAGE_AGENT_FORBIDDEN.get(s.stage, "")
        if forbidden and s.stage != Stage.DONE:
            lines.append(f"Агенту запрещено на этом этапе: {forbidden}")
        required = STAGE_REQUIRED_FIELDS.get(s.stage, ())
        if required:
            lines.append("Факты этапа (сообщает волонтёр; переход делает волонтёр):")
            for key in required:
                label = FIELD_LABELS.get(key, key)
                val = s.stage_data.get(key)
                if _field_filled(s.stage_data, key):
                    lines.append(f"  ✓ {label}: {val}")
                else:
                    lines.append(f"  · {label}: (ещё нет)")
            lines.append(
                "Когда волонтёр готов закрыть этап — он явно говорит об этом "
                "(«бриф готов», «можем идти дальше»). Ты этап не переключаешь."
            )
        if s.artifacts:
            lines.append("Закрытые этапы (документы):")
            for art in s.artifacts:
                lines.append(
                    f"- [{art.status}] {art.title} ({art.type}, {art.stage.value})"
                )
        lines.append(
            "Порядок: pitch → welfare_check → rehearsal → publish → done. "
            "Перескакивать нельзя."
        )
        return "\n".join(lines)

    def format_stdout(self) -> str:
        if self.state is None:
            return "[state] (нет активной съёмки)"
        s = self.state
        pause = " paused" if s.paused else ""
        return (
            f"[state] stage={s.stage.value} | step={s.step} | expected={s.expected_action}{pause}"
        )

    def dump_section(self) -> str:
        if self.state is None:
            return "=== FSM (TikTok-съёмка) ===\n  (нет кейса)"
        s = self.state
        lines = [
            "=== FSM (TikTok-съёмка) ===",
            f"  {s.opossum} — {s.applicant}",
            f"  stage={s.stage.value} paused={s.paused}",
            f"  step: {s.step}",
            f"  expected: {s.expected_action}",
            f"  stage_data: {s.stage_data}",
        ]
        for art in s.artifacts:
            lines.append(f"  doc: {art.type} «{art.title}» ({art.status}, {art.by})")
        return "\n".join(lines)


def apply_fsm_event(
    store: TaskStateStore,
    fsm: dict[str, Any] | None,
    profile_id: str,
) -> list[str]:
    """Применить событие FSM из классификатора (только по реплике пользователя)."""
    if store.state is None or not fsm or not isinstance(fsm, dict):
        return []
    event = str(fsm.get("event") or "").strip().lower()
    if not event or event == "null":
        return []

    applied: list[str] = []

    if event == "update_step":
        store.update_step(
            step=str(fsm.get("step") or "").strip() or None,
            expected_action=str(fsm.get("expected_action") or "").strip() or None,
            stage_data=fsm.get("stage_data") if isinstance(fsm.get("stage_data"), dict) else None,
        )
        applied.append("update_step")
        if isinstance(fsm.get("stage_data"), dict) and fsm["stage_data"]:
            keys = ", ".join(sorted(fsm["stage_data"]))
            applied.append(f"stage_data +{keys}")
        return applied

    if event == "complete_stage":
        stage_data = fsm.get("stage_data")
        if isinstance(stage_data, dict) and stage_data:
            store.update_step(stage_data=stage_data)
            keys = ", ".join(sorted(stage_data))
            applied.append(f"stage_data +{keys}")
        missing = store.missing_fields()
        if missing:
            labels = ", ".join(FIELD_LABELS.get(k, k) for k in missing)
            applied.append(f"denied complete: не хватает {labels}")
            return applied
        ok, detail = store.request_advance(None)
        if ok:
            applied.append(f"allowed {detail}")
        else:
            applied.append(f"denied {detail}")
        return applied

    if event == "advance":
        target = parse_stage(str(fsm.get("target_stage") or "").strip() or None)
        ok, detail = store.request_advance(target)
        if ok:
            applied.append(f"allowed {detail}")
        else:
            applied.append(f"denied {detail}")
        return applied

    if event == "pause":
        store.pause()
        applied.append("pause")
        return applied

    if event == "resume":
        store.resume()
        applied.append("resume")
        return applied

    return applied
