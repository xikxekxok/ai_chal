"""LLM-симулятор пользователей приюта (Марта, директор)."""

from __future__ import annotations

from dataclasses import dataclass

from llm import LlmConfig, UsageTracker, complete

MARTHA_KNOWLEDGE = """
Ты — Марта, смотритель ночной смены приюта «Хvостik».
Говоришь с операционным ассистентом смены о подопечных опossumах.
""".strip()

DIRECTOR_KNOWLEDGE = """
Ты — директор приюта «Хvостik». Даёшь распоряжения по регламенту и уставу.
Ассистент фиксирует изменения устава (long), не кадровые приказы в Excel.
""".strip()

MARTHA_SYSTEM = f"""\
Ты симулируешь МАРТУ — смотрителя ночного приюта опossumов «Хvостik».

{MARTHA_KNOWLEDGE}

Правила:
- 2–5 предложений, живой русский, лёгкий opossum-юмор уместен.
- Отвечай на последнюю реплику ассистента.
- Подсказки хода — вплетай в реплику.
- Ответ: ТОЛЬКО текст Марты, без кавычек и пояснений.
"""

DIRECTOR_SYSTEM = f"""\
Ты симулируешь ДИРЕКТОРА приюта опossumов «Хvостik».

{DIRECTOR_KNOWLEDGE}

Правила:
- Кратко, по-деловому, 1–3 предложения.
- Ответ: ТОЛЬКО текст директора, без кавычек и пояснений.
"""

DIALOG_SCENARIOS = {
    "intake": (
        "Сценарий: приём нового опossuma Пушка. Сообщай факты по одному: "
        "кто, где нашли, вес, состояние, карантин."
    ),
    "next_day": (
        "Сценарий: следующий день после приёма Пушка. "
        "Спрашивай как он, сообщай аппетит/активность, спрашивай про усыновление и recall."
    ),
    "director": (
        "Сценарий: изменение часов работы приюта в уставе. "
        "Новая смена 18:00–08:00 с нового месяца."
    ),
}


@dataclass
class SimTurn:
    label: str
    hints: list[str]


@dataclass
class UserSimulator:
    config: LlmConfig
    persona: str
    scenario: str = ""
    prior_summary: str = ""
    tracker: UsageTracker | None = None

    def _system(self) -> str:
        base = DIRECTOR_SYSTEM if self.persona == "director" else MARTHA_SYSTEM
        scene = DIALOG_SCENARIOS.get(self.scenario, "")
        if scene:
            return f"{base}\n\nТекущий сценарий: {scene}"
        return base

    def generate(
        self,
        transcript: list[dict[str, str]],
        *,
        turn: SimTurn,
    ) -> str:
        topics = ", ".join(turn.hints) if turn.hints else "продолжай диалог"
        hint = f"Ход: {turn.label}. Обязательно раскрой: {topics}."

        if not transcript:
            hint = f"{hint} Начни новый диалог с ассистентом."

        if transcript:
            lines = []
            for msg in transcript:
                label = "Ты" if msg["role"] == "user" else "Ассистент"
                lines.append(f"{label}: {msg['content']}")
            history = "Текущий диалог (полностью):\n\n" + "\n\n".join(lines)
        else:
            history = "(текущий диалог только начинается — реплик ассистента ещё нет)"

        prior_block = ""
        if self.prior_summary.strip():
            prior_block = (
                "Память о прошлых сменах (саммари — детали диалогов забыты):\n"
                f"{self.prior_summary.strip()}\n\n"
            )

        messages = [
            {"role": "system", "content": self._system()},
            {
                "role": "user",
                "content": (
                    f"{prior_block}{history}\n\n{hint}\n\n"
                    "Напиши следующую реплику (только текст)."
                ),
            },
        ]
        text, _ = complete(self.config, messages, tracker=self.tracker)
        return text.strip()


def dialog1_turns() -> list[SimTurn]:
    return [
        SimTurn("1", ["принесли опossuma", "зовут Пушок", "нашли у дороги"]),
        SimTurn("2", ["вес около 1.2 кг", "вялый", "без видимых ран"]),
        SimTurn("3", ["положили в карантин", "день 1 карантина"]),
        SimTurn("4", ["устала", "дождь", "болтовня без новых фактов о животных"]),
    ]


def dialog2_turns() -> list[SimTurn]:
    return [
        SimTurn("1", ["как Пушок после ночи", "спроси статус"]),
        SimTurn("2", ["Пушок сегодня ел нормально", "активнее чем вчера"]),
        SimTurn("3", ["когда можно отдавать Пушка в семью"]),
        SimTurn("4", ["что зафиксировали по Пушку", "перечисли факты"]),
    ]


def dialog3_turns() -> list[SimTurn]:
    return [
        SimTurn("1", ["с нового месяца смена 18:00–08:00", "зафиксируй в уставе приюта"]),
        SimTurn("2", ["подтверди новые рабочие часы приюта"]),
    ]
