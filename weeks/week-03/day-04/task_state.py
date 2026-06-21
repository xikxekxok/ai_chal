"""FSM активной заявки на выдачу опossuma — этап, шаг, документы-артефакты."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

VALID_ARTIFACT_STATUSES = frozenset({"draft", "approved", "signed", "filed"})


class Stage(StrEnum):
    APPLICATION_REVIEW = "application_review"
    HOME_VISIT = "home_visit"
    TRIAL_PERIOD = "trial_period"
    VET_CLEARANCE = "vet_clearance"
    CONTRACT = "contract"
    DONE = "done"


STAGE_ORDER: list[Stage] = [
    Stage.APPLICATION_REVIEW,
    Stage.HOME_VISIT,
    Stage.TRIAL_PERIOD,
    Stage.VET_CLEARANCE,
    Stage.CONTRACT,
    Stage.DONE,
]

STAGE_EXIT_ARTIFACTS: dict[Stage, str] = {
    Stage.APPLICATION_REVIEW: "adoption_application",
    Stage.HOME_VISIT: "home_visit_act",
    Stage.TRIAL_PERIOD: "trial_period_report",
    Stage.VET_CLEARANCE: "vet_examination_protocol",
    Stage.CONTRACT: "adoption_contract",
}

STAGE_DEFAULTS: dict[Stage, dict[str, str]] = {
    Stage.APPLICATION_REVIEW: {
        "step": "Сверить анкету с уставом",
        "expected_action": "Смотритель: проверить анкету и условия содержания",
    },
    Stage.HOME_VISIT: {
        "step": "Провести домашний визит",
        "expected_action": "Смотритель: согласовать дату и адрес визита, оформить акт",
    },
    Stage.TRIAL_PERIOD: {
        "step": "Наблюдение в семье",
        "expected_action": "Смотритель: контролировать пробный период, подготовить отчёт",
    },
    Stage.VET_CLEARANCE: {
        "step": "Осмотр перед выдачей",
        "expected_action": "Ветеринар: провести осмотр, оформить протокол",
    },
    Stage.CONTRACT: {
        "step": "Подписание договора",
        "expected_action": "Смотритель: подписать договор об усыновлении с семьёй",
    },
    Stage.DONE: {
        "step": "Кейс закрыт",
        "expected_action": "Выдача завершена",
    },
}

STAGE_LABELS: dict[Stage, str] = {
    Stage.APPLICATION_REVIEW: "проверка анкеты",
    Stage.HOME_VISIT: "домашний визит",
    Stage.TRIAL_PERIOD: "пробный период",
    Stage.VET_CLEARANCE: "ветеринарный осмотр",
    Stage.CONTRACT: "подписание договора",
    Stage.DONE: "завершено",
}


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
        try:
            stage = Stage(str(data.get("stage", "")))
        except ValueError:
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
        try:
            stage = Stage(str(data.get("stage", "")))
        except ValueError:
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
        defaults = STAGE_DEFAULTS[Stage.APPLICATION_REVIEW]
        self.state = TaskState(
            case_id=f"{opossum.lower()}-{applicant.lower().replace(' ', '-')}",
            opossum=opossum.strip(),
            applicant=applicant.strip(),
            stage=Stage.APPLICATION_REVIEW,
            step=defaults["step"],
            expected_action=defaults["expected_action"],
            paused=False,
        )
        self.save()
        return self.state

    def has_exit_artifact(self, stage: Stage | None = None) -> bool:
        if self.state is None:
            return False
        target = stage or self.state.stage
        required = STAGE_EXIT_ARTIFACTS.get(target)
        if not required:
            return False
        return any(
            a.type == required and a.status in VALID_ARTIFACT_STATUSES for a in self.state.artifacts
        )

    def get_artifact(self, doc_type: str) -> Artifact | None:
        if self.state is None:
            return None
        for art in reversed(self.state.artifacts):
            if art.type == doc_type:
                return art
        return None

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

    def advance(self) -> tuple[bool, str]:
        if self.state is None:
            return False, "нет активного кейса"
        current = self.state.stage
        if current == Stage.DONE:
            return False, "кейс уже завершён"
        if not self.has_exit_artifact(current):
            required = STAGE_EXIT_ARTIFACTS.get(current, "?")
            return False, f"нет exit-документа «{required}» для этапа {current.value}"
        try:
            idx = STAGE_ORDER.index(current)
        except ValueError:
            return False, f"неизвестный этап {current.value}"
        if idx + 1 >= len(STAGE_ORDER):
            return False, "нет следующего этапа"
        next_stage = STAGE_ORDER[idx + 1]
        defaults = STAGE_DEFAULTS[next_stage]
        self.state.stage = next_stage
        self.state.step = defaults["step"]
        self.state.expected_action = defaults["expected_action"]
        self.state.paused = False
        self.save()
        return True, next_stage.value

    def missing_exit_label(self) -> str | None:
        if self.state is None or self.state.stage == Stage.DONE:
            return None
        required = STAGE_EXIT_ARTIFACTS.get(self.state.stage)
        if required and not self.has_exit_artifact():
            labels = {
                "adoption_application": "Анкета (одобренная)",
                "home_visit_act": "Акт домашнего визита",
                "trial_period_report": "Отчёт о пробном периоде",
                "vet_examination_protocol": "Протокол осмотра",
                "adoption_contract": "Договор об усыновлении",
            }
            return labels.get(required, required)
        return None

    def to_prompt_block(self) -> str:
        if self.state is None:
            return "(активной заявки нет)"
        s = self.state
        status = "ПАУЗА" if s.paused else "в работе"
        lines = [
            f"Кейс: выдача **{s.opossum}** → **{s.applicant}**",
            f"Этап: {s.stage.value} ({STAGE_LABELS.get(s.stage, s.stage.value)})",
            f"Шаг: {s.step}",
            f"Ожидается: {s.expected_action}",
            f"Статус: {status}",
        ]
        if s.stage_data:
            facts = ", ".join(f"{k}: {v}" for k, v in sorted(s.stage_data.items()))
            lines.append(f"Факты этапа: {facts}")
        if s.artifacts:
            lines.append("Документы кейса:")
            for art in s.artifacts:
                lines.append(
                    f"- [{art.status}] {art.title} ({art.type}, {art.stage.value}, {art.by})"
                )
        else:
            lines.append("Документы кейса: (пока нет)")
        missing = self.missing_exit_label()
        if missing:
            lines.append(f"Для перехода с этапа нужен документ: {missing}")
        lines.append(
            "Не перескакивай этапы. Не меняй заявителя активного кейса без закрытия кейса."
        )
        return "\n".join(lines)

    def format_stdout(self) -> str:
        if self.state is None:
            return "[state] (нет активного кейса)"
        s = self.state
        pause = " paused" if s.paused else ""
        return (
            f"[state] stage={s.stage.value} | step={s.step} | "
            f"expected={s.expected_action}{pause}"
        )

    def dump_section(self) -> str:
        if self.state is None:
            return "=== FSM (активная заявка) ===\n  (нет кейса)"
        s = self.state
        lines = [
            "=== FSM (активная заявка) ===",
            f"  {s.opossum} → {s.applicant}",
            f"  stage={s.stage.value} paused={s.paused}",
            f"  step: {s.step}",
            f"  expected: {s.expected_action}",
        ]
        for art in s.artifacts:
            lines.append(f"  doc: {art.type} «{art.title}» ({art.status}, {art.by})")
        return "\n".join(lines)


def apply_fsm_event(
    store: TaskStateStore,
    fsm: dict[str, Any] | None,
    profile_id: str,
) -> list[str]:
    """Применить событие FSM из классификатора. Возвращает строки для stdout."""
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
        return applied

    if event == "add_artifact":
        raw = fsm.get("artifact")
        if not isinstance(raw, dict):
            return applied
        doc_type = str(raw.get("type") or "").strip()
        if not doc_type:
            return applied
        art = store.add_artifact(
            doc_type=doc_type,
            title=str(raw.get("title") or doc_type).strip(),
            summary=str(raw.get("summary") or "").strip(),
            status=str(raw.get("status") or "approved").strip(),
            by=str(raw.get("by") or profile_id).strip(),
        )
        if art:
            applied.append(
                f"document + {art.type} «{art.title}» ({art.status}, {art.by})"
            )
            exit_type = STAGE_EXIT_ARTIFACTS.get(store.state.stage)
            if exit_type == doc_type and store.has_exit_artifact():
                ok, detail = store.advance()
                if ok:
                    applied.append(f"→ advance {detail}")
                else:
                    applied.append(f"✗ advance: {detail}")
        return applied

    if event == "advance":
        ok, detail = store.advance()
        if ok:
            applied.append(f"→ advance {detail}")
        else:
            applied.append(f"✗ advance: {detail}")
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
