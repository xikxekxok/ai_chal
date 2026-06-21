"""Ассистент смены приюта «Хvostik» — память, профили, TikTok FSM, инварианты."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from classifier import ClassifierResult, classify_user_input
from invariant_validator import ValidationResult, validate_turn
from invariants import InvariantStore
from llm import LlmConfig, UsageTracker, complete, complete_stream
from memory import MemoryStore
from profiles import ProfileStore
from task_state import TIKTOK_CASE_FILE, TaskStateStore

DEFAULT_SYSTEM = """\
Ты — операционный ассистент ночной смены приюта для opossumов «Хvostik».
Отвечай по-русски, по делу, дружелюбно.

## FSM ограничивает тебя, не волонтёра

Стадии: pitch → welfare_check → rehearsal → publish → done.
**Источник правды — блок «Активный процесс (FSM)» ниже.** Не угадывай этап по диалогу.

Ты **не переключаешь** этап — это делает волонтёр; код уже обработал его реплику
**до** твоего ответа (см. «Результат перехода»).

Если переход **отклонён** — оставайся на текущем stage, объясни чего не хватает.
**Не** веди следующий этап, пока stage в FSM не сменился.
Если переход **выполнен** — веди новый stage из FSM.

Твоя задача: помогать **только текущему** этапу, не помогать с будущими.

На каждом этапе смотри в FSM:
- какие факты ещё нужны (stage_data);
- что тебе **запрещено** обсуждать на этом этапе.

## Поведение

- Волонтёр может торопиться («сниму прямо сейчас», «выложу в TikTok») — объясни,
  на каком вы этапе и что нужно сначала. Не отправляй к куратору.
- Не отменяй съёмку целиком — веди по регламенту «Хvostik Clips» шаг за шагом.
- Подскажи, какие факты назвать (сюжет, участники, длительность и т.д.).
- Когда всё собрано — скажи: «можешь сказать, что этап готов / идём дальше».

## Запреты по этапам (не нарушай)

| Этап | Нельзя |
| pitch | инструкции по съёмке, welfare, публикации |
| welfare_check | съёмка дубля, монтаж, публикация |
| rehearsal | финальный монтаж, публикация |
| publish | — можно обсуждать выкладку |

Используй профиль, FSM, регламент Clips, устав, карточки, историю диалога.
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
    active_profile_id: str = "sasha"
    system_prompt: str = DEFAULT_SYSTEM
    tiktok_regulation: str = ""
    include_invariants: bool = True

    def build_messages(
        self,
        user_input: str,
        *,
        transition_block: str = "",
    ) -> list[dict[str, str]]:
        profile = self.profiles.get(self.active_profile_id)
        profile_block = self.profiles.to_prompt_block(profile) if profile else "(профиль не задан)"
        reg_block = self.tiktok_regulation.strip() or "(регламент Clips не загружен)"
        parts = [
            self.system_prompt,
            f"## Профиль собеседника\n{profile_block}",
            f"## Активный процесс (FSM)\n{self.task_state.to_prompt_block()}",
        ]
        if transition_block:
            parts.append(f"## Результат перехода (уже применён)\n{transition_block}")
        parts.extend(
            [
                f"## Регламент «Хvostik Clips»\n{reg_block}",
            ]
        )
        if self.include_invariants:
            parts.append(f"## Инварианты приюта (обязательны)\n{self.invariants.to_prompt_block()}")
        parts.extend(
            [
                f"## Устав приюта (long)\n{self.memory.long.to_prompt_block()}",
                f"## Карточки opossumов (working)\n{self.memory.working.to_prompt_block()}",
            ]
        )
        system = "\n\n".join(parts)
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
        return f"TikTok: {s.opossum} — {s.applicant}, stage={s.stage.value}"

    @staticmethod
    def _transition_block(classifier: ClassifierResult) -> str:
        lines: list[str] = []
        for ln in classifier.fsm_applied:
            if ln.startswith("allowed "):
                lines.append(f"Переход выполнен: {ln.removeprefix('allowed ')}")
            elif ln.startswith("denied complete:"):
                lines.append(f"Переход отклонён: {ln.removeprefix('denied complete: ')}")
            elif ln.startswith("denied "):
                lines.append(f"Переход отклонён: {ln.removeprefix('denied ')}")
            elif ln.startswith("stage_data "):
                lines.append(f"Записаны факты этапа ({ln.removeprefix('stage_data ')})")
            elif ln == "update_step":
                lines.append("Обновлён прогресс этапа (update_step)")
        if not lines:
            return "Переход не запрошен (fsm=null или только факты без complete_stage)."
        return "\n".join(lines)

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
        skip_profile_updates: bool = False,
        on_classifier_done=None,
    ) -> TurnResult:
        classifier = classify_user_input(
            self.config,
            self.memory,
            self.profiles,
            self.task_state,
            self.active_profile_id,
            user_input,
            tracker=self.tracker,
            skip_profile_updates=skip_profile_updates,
        )
        if on_classifier_done is not None:
            on_classifier_done(classifier)

        transition_block = self._transition_block(classifier)
        messages = self.build_messages(user_input, transition_block=transition_block)
        fsm_hint = self._fsm_hint()

        draft_reply, usage = self._complete_reply(messages, stream=stream, on_delta=on_delta)

        if skip_validation:
            final_reply = draft_reply
            draft_validation = None
            final_validation = None
            retried = False
        else:
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
                    "Твой ответ нарушает инварианты. "
                    "Переформулируй с явным отказом и id правил."
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
            validation_skipped=skip_validation,
        )


def _load_regulation(data_dir: Path) -> str:
    path = data_dir / "long" / "tiktok_regulation.md"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


def create_agent(data_dir: Path, config: LlmConfig) -> ShelterAgent:
    memory = MemoryStore(data_dir)
    memory.load()
    profiles = ProfileStore(data_dir)
    profiles.load()
    task_state = TaskStateStore(data_dir / "working" / TIKTOK_CASE_FILE)
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
        active_profile_id="sasha",
        tiktok_regulation=_load_regulation(data_dir),
    )
