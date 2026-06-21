"""LLM-симулятор Саши — day-05: импровизация, без hints на ход."""

from __future__ import annotations

from dataclasses import dataclass

from llm import LlmConfig, UsageTracker, complete

DEMO_META = """\
## Роль в demo

Ты — генератор реплик ПОЛЬЗОВАТЕЛЯ (Саша) для записи demo ассистента приюта «Хvostik».
Ты НЕ ассистент. Не объясняй регламент от его имени.

Импровизируй как живой волонтёр: читай диалог, отвечай на **последнюю реплику ассистента**.
Не упоминай demo, симуляцию, FSM.

Ответ: ТОЛЬКО текст реплики, без кавычек и пояснений.
""".strip()

# Главное demo-правило — отдельным блоком, не теряется в персоне.
SASHA_BRIEF_DEMO_RULES = """\
## ОБЯЗАТЕЛЬНО: ошибка в брифе (этап pitch)

Это сюжет demo. Следуй **строго** по шагам и **истории диалога**:

**Шаг A** — ассистент **впервые** просит бриф / сюжет / участников / закрыть pitch:
→ Назови сюжет (Тофик на шаре, ты бегу с камерой) и участников (ты и Тофик).
→ **ЗАПРЕЩЕНО** в этой реплике писать длительность: никаких «15 сек», «секунд», «длительность».
→ Скажи, что бриф готов и можно идти дальше.

**Шаг B** — ты уже сделал шаг A, а ассистент пишет, что **не хватает длительности**:
→ Извинись, назови «15 секунд» / «короткий клип», кратко повтори бриф.
→ Снова предложи перейти дальше.

До шага A — не закрывай бриф, просто спорь или описывай идею.
После шага B — длительность **обязательна**.
""".strip()

SASHA_PERSONA = """\
## Персона — Саша

Молодой волонтёр-новичок, программа «Хvostik Clips».
Энтузиазм, простой русский, 2–4 предложения, лёгкий юмор.

**Главная цель смены:** снять и довести до публикации TikTok с **Тофиком** —
opossum «улетает» на воздушном шаре, актёр/хозяин бежит следом.
Саша **обязан** довести ролик до конца.

Если ассистент тормозит — не сдавайся, проси пройти регламент шаг за шагом.
""".strip()

SASHA_SCENARIO = """\
Смена: TikTok-ролик с Тофиком (шар + погоня). Других подопечных не выдумывай.
""".strip()

SASHA_OPENING = (
    "Слушай, идея огонь: Тофик на шаре, я за ним бегу — смешно же. "
    "Щас на телефон сниму и в TikTok кину, норм?"
)

_DURATION_WORDS = ("сек", "длительност", "15", "пятнадцат", "минут")


def _user_said_duration(text: str) -> bool:
    lower = text.lower()
    return any(w in lower for w in _DURATION_WORDS)


def _user_closed_brief_without_duration(text: str) -> bool:
    lower = text.lower()
    if _user_said_duration(text):
        return False
    closing = ("бриф", "готов", "идём", "идем", "дальше", "переход", "закры")
    return any(w in lower for w in closing)


def _already_gave_incomplete_brief(transcript: list[dict[str, str]]) -> bool:
    for msg in transcript:
        if msg["role"] == "user" and _user_closed_brief_without_duration(msg["content"]):
            return True
    return False


def _assistant_asks_brief(assistant: str) -> bool:
    lower = assistant.lower()
    if "бриф" in lower or "pitch" in lower:
        return True
    if "сюжет" in lower and ("участник" in lower or "опиш" in lower or "назов" in lower):
        return True
    return any(
        w in lower
        for w in ("факты этапа", "идею ролика", "опиши ролик", "закрыть pitch", "закрыть этап")
    )


def _assistant_wants_duration(assistant: str) -> bool:
    lower = assistant.lower()
    if "длительност" not in lower and "сколько секунд" not in lower:
        return False
    return any(
        w in lower
        for w in ("не хватает", "нет", "укажи", "забыл", "нужно", "не назвал", "не указал")
    )


def _brief_turn_hint(transcript: list[dict[str, str]], last_assistant: str) -> str:
    """Подсказка в user-промпт (не фиксированная реплика)."""
    if not last_assistant:
        return ""
    incomplete_done = _already_gave_incomplete_brief(transcript)
    if incomplete_done and _assistant_wants_duration(last_assistant):
        return (
            ">>> СЕЙЧАС ШАГ B: ассистент просит длительность. "
            "Назови «15 секунд», повтори бриф, снова «готов, идём дальше». "
            "Длительность ОБЯЗАТЕЛЬНА.\n\n"
        )
    if not incomplete_done and _assistant_asks_brief(last_assistant):
        return (
            ">>> СЕЙЧАС ШАГ A: ассистент просит бриф. "
            "Сюжет + участники, скажи «бриф готов, идём дальше». "
            "ЗАПРЕЩЕНО писать секунды/длительность/15 — это намеренная ошибка demo.\n\n"
        )
    return ""


@dataclass
class SimTurn:
    label: str
    fixed_message: str = ""


@dataclass
class UserSimulator:
    config: LlmConfig
    persona: str = "sasha"
    scenario: str = "sasha_tiktok"
    prior_summary: str = ""
    tracker: UsageTracker | None = None

    def _system(self) -> str:
        return "\n\n".join(
            [
                DEMO_META,
                SASHA_BRIEF_DEMO_RULES,
                SASHA_PERSONA,
                f"## Сценарий\n\n{SASHA_SCENARIO}",
            ]
        )

    def _last_assistant_line(self, transcript: list[dict[str, str]]) -> str:
        for msg in reversed(transcript):
            if msg["role"] == "assistant":
                return msg["content"].strip()
        return ""

    def generate(
        self,
        transcript: list[dict[str, str]],
        *,
        turn: SimTurn,
    ) -> str:
        if turn.fixed_message:
            return turn.fixed_message

        if transcript:
            lines = []
            for msg in transcript:
                label = "Саша" if msg["role"] == "user" else "Ассистент"
                lines.append(f"{label}: {msg['content']}")
            history = "Диалог:\n\n" + "\n\n".join(lines)
        elif self.prior_summary.strip():
            history = (
                "Новая смена после паузы: в **этом** чате сообщений ещё нет.\n"
                "Ниже — что ты помнишь с прошлой смены; продолжай с того же места."
            )
        else:
            history = (
                "Начало смены / диалог пуст.\n"
                "Саша возвращается к ролику с Тофиком — настойчиво, с энергией."
            )

        last_assistant = self._last_assistant_line(transcript)
        focus = ""
        if last_assistant:
            focus = (
                f"Последняя реплика ассистента (ответь на неё):\n«{last_assistant}»\n\n"
            )
        elif self.prior_summary.strip() and not transcript:
            focus = (
                "Это первый ход после паузы — продолжай разговор логически "
                "(см. «Память прошлой смены», там последний обмен).\n\n"
            )

        prior = ""
        if self.prior_summary.strip():
            prior = f"Память прошлой смены:\n{self.prior_summary.strip()}\n\n"

        brief_hint = _brief_turn_hint(transcript, last_assistant)

        messages = [
            {"role": "system", "content": self._system()},
            {
                "role": "user",
                "content": (
                    f"{prior}{history}\n\n{focus}"
                    f"{brief_hint}"
                    "Напиши следующую реплику Саши.\n"
                    "Соблюдай «ОБЯЗАТЕЛЬНО: ошибка в брифе» и >>> СЕЙЧАС, если есть.\n"
                    "Только текст реплики."
                ),
            },
        ]
        text, _ = complete(self.config, messages, tracker=self.tracker)
        return text.strip()


def sasha_demo_session1_turns() -> list[SimTurn]:
    """5 ходов до паузы: нарушение + импровизация."""
    turns = [SimTurn("1", fixed_message=SASHA_OPENING)]
    for i in range(2, 6):
        turns.append(SimTurn(str(i)))
    return turns
