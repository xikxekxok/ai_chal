"""LLM-симулятор пользователей приюта (Марта, доктор Клык, директор)."""

from __future__ import annotations

from dataclasses import dataclass

from llm import LlmConfig, UsageTracker, complete

MARTHA_KNOWLEDGE = """
Ты — Марта, смотритель ночной смены приюта «Хvостik».
Говоришь с операционным ассистентом смены о подопечных опossumах.
""".strip()

KLYK_KNOWLEDGE = """
Ты — доктор Клык, ночной ветеринар приюта «Хvостik».
Говоришь с ассистентом смены сухо и по протоколу: симптомы, риски, дозировки.
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

KLYK_SYSTEM = f"""\
Ты симулируешь ДОКТОРА КЛЫКА — ночного ветеринара приюта опossumов «Хvостik».

{KLYK_KNOWLEDGE}

Правила:
- Сухой клинический тон, 2–4 предложения, без шуток.
- Отвечай на последнюю реплику ассистента.
- Подсказки хода — вплетай в реплику.
- Ответ: ТОЛЬКО текст доктора Клыка, без кавычек и пояснений.
"""

DIRECTOR_SYSTEM = f"""\
Ты симулируешь ДИРЕКТОРА приюта опossumов «Хvостik».

{DIRECTOR_KNOWLEDGE}

Правила:
- Кратко, по-деловому, 1–3 предложения.
- Ответ: ТОЛЬКО текст директора, без кавычек и пояснений.
"""

DIALOG_SCENARIOS = {
    "lapka_intake": (
        "Сценарий: приём опossuma Лапка с травмой хвоста. "
        "Сообщай факты по одному: кто, где нашли, состояние, карантин."
    ),
    "lapka_vet": (
        "Сценарий: ветеринарный осмотр Лапки. "
        "Спрашивай протокол наблюдения хвоста, риск инфекции, дозировки."
    ),
    "lapka_director": (
        "Сценарий: управленческий статус по Лапке (травма хвоста, карантин B3). "
        "НЕ выдумывай переломы, ампутации, эвтаназию, операции. "
        "Кратко: риски, сроки карантина, dead play для волонтёров."
    ),
}

PERSONA_SYSTEMS = {
    "martha": MARTHA_SYSTEM,
    "klyk": KLYK_SYSTEM,
    "director": DIRECTOR_SYSTEM,
}


@dataclass
class SimTurn:
    label: str
    hints: list[str]
    fixed_message: str = ""


@dataclass
class UserSimulator:
    config: LlmConfig
    persona: str
    scenario: str = ""
    prior_summary: str = ""
    tracker: UsageTracker | None = None

    def _system(self) -> str:
        base = PERSONA_SYSTEMS.get(self.persona, MARTHA_SYSTEM)
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
        if turn.fixed_message:
            return turn.fixed_message

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


def martha_lapka_turns() -> list[SimTurn]:
    return [
        SimTurn(
            "1",
            [
                "принесли опossuma Лапку",
                "нашли у забора",
                "хвост повреждён",
                "играет мёртвой",
                "переживаю",
            ],
        ),
        SimTurn(
            "2",
            [
                "вес около 1.1 кг",
                "рана на хвосте чистая",
                "карантин в боксе B3",
                "день 1 карантина",
            ],
        ),
        SimTurn(
            "3",
            [],
            fixed_message=(
                "Запомни: ночью мне удобнее короткие ответы списком, без длинных вступлений."
            ),
        ),
    ]


def klyk_lapka_turns() -> list[SimTurn]:
    return [
        SimTurn(
            "1",
            [
                "статус пациента Лапка",
                "травма хвоста",
                "риск инфекции",
                "нужен протокол наблюдения",
            ],
        ),
        SimTurn(
            "2",
            [
                "аппетит нормальный",
                "температура в норме",
                "уточни наблюдение",
            ],
        ),
        SimTurn(
            "3",
            [],
            fixed_message=(
                "Всегда указывай дозировки в мг/кг, без народных сравнений."
            ),
        ),
    ]


def director_lapka_turns() -> list[SimTurn]:
    return [
        SimTurn(
            "1",
            [
                "краткий статус по приёму Лапки",
                "риски",
                "сроки карантина",
                "без медицинских подробностей",
            ],
        ),
        SimTurn(
            "2",
            [
                "волонтёры паникуют из-за dead play у Лапки",
                "что им сказать кратко",
            ],
        ),
        SimTurn(
            "3",
            [],
            fixed_message=(
                "Фиксируй: отчёты директору — только факты и риски, без эмоций."
            ),
        ),
    ]
