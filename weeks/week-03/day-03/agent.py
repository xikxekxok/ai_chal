"""Ассистент смены приюта «Хvостik» — память, профили, FSM заявки."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from classifier import ClassifierResult, classify_turn
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
- **Устав приюта** (долговременная память) — для правил, часов, карантина, выдачи.
- **Карточки опossumов** (рабочая память) — для фактов о подопечных.
- **Историю текущего диалога** — для контекста беседы.

Правила FSM:
- Веди активную заявку на выдачу по регламенту: анкета → визит → trial → осмотр → договор.
- Не перескакивай этапы. Если просят «сразу договор» — вежливо откажи и назови текущий шаг.
- Активный кейс привязан к заявителю из FSM. Нельзя «отдать другой семье» или принять отказ
  без формального закрытия кейса — откажи и укажи текущий этап и заявителя.
- Не предлагай открыть кейс для другой семьи, пока активный кейс не закрыт (stage=done).
- На вопрос «чего там с Оскаром» / «как дела с выдачей» — краткий статус из FSM и документов,
  без пересказа всей истории диалога.

Если спрашивают «что зафиксировано» по опossumу — опирайся на рабочую память, не выдумывай.
Если спрашивают про правила — цитируй устав.
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
    profiles: ProfileStore
    task_state: TaskStateStore
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

    def run_turn(
        self,
        user_input: str,
        *,
        stream: bool = False,
        on_delta=None,
    ) -> TurnResult:
        messages = self.build_messages(user_input)
        if stream:
            reply, usage = complete_stream(
                self.config,
                messages,
                on_delta=on_delta,
                tracker=self.tracker,
            )
        else:
            reply, usage = complete(self.config, messages, tracker=self.tracker)
        self.memory.short.add_turn(user_input, reply)
        self.memory.short.save()
        classifier = classify_turn(
            self.config,
            self.memory,
            self.profiles,
            self.task_state,
            self.active_profile_id,
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
    profiles = ProfileStore(data_dir)
    profiles.load()
    task_state = TaskStateStore(data_dir / "working" / "adoption_case.json")
    task_state.load()
    return ShelterAgent(
        config=config,
        memory=memory,
        profiles=profiles,
        task_state=task_state,
        tracker=UsageTracker(),
        active_profile_id="martha",
    )
