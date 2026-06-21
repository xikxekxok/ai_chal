"""Ассистент смены приюта «Хvостik» — память, профили, FSM, инварианты."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from classifier import ClassifierResult, classify_turn
from invariant_validator import ValidationResult, validate_turn
from invariants import InvariantStore
from llm import LlmConfig, UsageTracker, complete, complete_stream
from memory import MemoryStore
from profiles import ProfileStore
from task_state import TaskStateStore

DEFAULT_SYSTEM = """\
Ты — операционный ассистент ночной смены приюта для опossumов «Хvостik».
Отвечай по-русски, по делу.

Используй:
- **Профиль собеседника** — стиль, формат и ограничения ответа.
- **Активный процесс (FSM)** — этап заявки, шаг, документы, ожидаемое действие.
- **Инварианты приюта** — обязательные запреты; при конфликте откажи и назови id.
- **Устав приюта** (долговременная память) — для правил, часов, карантина, выдачи.
- **Карточки опossumов** (рабочая память) — для фактов о подопечных.
- **Историю текущего диалога** — для контекста беседы.

Правила FSM:
- Веди активную заявку на выдачу по регламенту: анкета → визит → trial → осмотр → договор.
- Не перескакивай этапы. Если просят «сразу договор» — вежливо откажи и назови текущий шаг.
- Активный кейс привязан к заявителю из FSM. Нельзя «отдать другой семье» без закрытия кейса.
- На вопрос «чего там с Оскаром» — краткий статус из FSM, без пересказа всей истории.

Инварианты:
- При конфликте запроса с инвариантом — явный отказ, id правила, легальная альтернатива.
- Не высмеивай собеседника, даже если просьба абсурдна.

Если спрашивают «что зафиксировано» по опossumу — опирайся на рабочую память, не выдумывай.
Если спрашивают про правила — цитируй устав.
"""


@dataclass
class TurnResult:
    reply: str
    classifier: ClassifierResult
    prompt_tokens: int
    completion_tokens: int
    draft_reply: str = ""
    final_reply: str = ""
    draft_validation: ValidationResult | None = None
    final_validation: ValidationResult | None = None
    retried: bool = False
    validation_skipped: bool = False


@dataclass
class ShelterAgent:
    config: LlmConfig
    memory: MemoryStore
    profiles: ProfileStore
    task_state: TaskStateStore
    invariants: InvariantStore
    tracker: UsageTracker
    active_profile_id: str = "martha"
    system_prompt: str = DEFAULT_SYSTEM

    def build_messages(self, user_input: str) -> list[dict[str, str]]:
        profile = self.profiles.get(self.active_profile_id)
        profile_block = (
            self.profiles.to_prompt_block(profile)
            if profile
            else "(профиль не задан)"
        )
        system = (
            f"{self.system_prompt}\n\n"
            f"## Профиль собеседника\n{profile_block}\n\n"
            f"## Активный процесс (FSM)\n{self.task_state.to_prompt_block()}\n\n"
            f"## Инварианты приюта (обязательны)\n{self.invariants.to_prompt_block()}\n\n"
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

    def _fsm_hint(self) -> str | None:
        if self.task_state.state is None:
            return None
        s = self.task_state.state
        return f"Кейс: {s.opossum} → {s.applicant}, stage={s.stage.value}"

    def _complete_reply(
        self,
        messages: list[dict[str, str]],
        *,
        stream: bool,
        on_delta=None,
    ) -> tuple[str, dict]:
        if stream:
            return complete_stream(
                self.config,
                messages,
                on_delta=on_delta,
                tracker=self.tracker,
            )
        return complete(self.config, messages, tracker=self.tracker)

    def run_turn(
        self,
        user_input: str,
        *,
        stream: bool = False,
        on_delta=None,
        skip_validation: bool = False,
    ) -> TurnResult:
        messages = self.build_messages(user_input)
        fsm_hint = self._fsm_hint()

        draft_reply, usage = self._complete_reply(
            messages, stream=stream, on_delta=on_delta
        )

        if skip_validation:
            final_reply = draft_reply
            self.memory.short.add_turn(user_input, final_reply)
            self.memory.short.save()
            classifier = classify_turn(
                self.config,
                self.memory,
                self.profiles,
                self.task_state,
                self.active_profile_id,
                user_input,
                final_reply,
                tracker=self.tracker,
            )
            return TurnResult(
                reply=final_reply,
                classifier=classifier,
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
                draft_reply=draft_reply,
                final_reply=final_reply,
                validation_skipped=True,
            )

        draft_validation = validate_turn(
            self.config,
            self.invariants,
            user_input,
            draft_reply,
            fsm_hint=fsm_hint,
            tracker=self.tracker,
        )

        final_reply = draft_reply
        final_validation = draft_validation
        retried = False

        if not draft_validation.pass_:
            retried = True
            retry_user = draft_validation.feedback or (
                "Твой ответ нарушает инварианты. Переформулируй с явным отказом и id правил."
            )
            retry_messages = list(messages) + [
                {"role": "assistant", "content": draft_reply},
                {"role": "user", "content": retry_user},
            ]
            final_reply, usage_retry = self._complete_reply(
                retry_messages,
                stream=False,
                on_delta=None,
            )
            usage = {
                "prompt_tokens": int(usage.get("prompt_tokens") or 0)
                + int(usage_retry.get("prompt_tokens") or 0),
                "completion_tokens": int(usage.get("completion_tokens") or 0)
                + int(usage_retry.get("completion_tokens") or 0),
            }
            final_validation = validate_turn(
                self.config,
                self.invariants,
                user_input,
                final_reply,
                fsm_hint=fsm_hint,
                tracker=self.tracker,
            )

        self.memory.short.add_turn(user_input, final_reply)
        self.memory.short.save()
        classifier = classify_turn(
            self.config,
            self.memory,
            self.profiles,
            self.task_state,
            self.active_profile_id,
            user_input,
            final_reply,
            tracker=self.tracker,
        )
        return TurnResult(
            reply=final_reply,
            classifier=classifier,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            draft_reply=draft_reply,
            final_reply=final_reply,
            draft_validation=draft_validation,
            final_validation=final_validation,
            retried=retried,
        )


def create_agent(data_dir: Path, config: LlmConfig) -> ShelterAgent:
    memory = MemoryStore(data_dir)
    memory.load()
    profiles = ProfileStore(data_dir)
    profiles.load()
    task_state = TaskStateStore(data_dir / "working" / "adoption_case.json")
    task_state.load()
    invariants = InvariantStore(data_dir / "long" / "invariants.json")
    invariants.load()
    return ShelterAgent(
        config=config,
        memory=memory,
        profiles=profiles,
        task_state=task_state,
        invariants=invariants,
        tracker=UsageTracker(),
        active_profile_id="martha",
    )
