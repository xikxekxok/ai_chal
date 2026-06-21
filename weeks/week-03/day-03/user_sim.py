"""LLM-симулятор пользователей приюта (Марта, доктор Клык, директор)."""

from __future__ import annotations

from dataclasses import dataclass, field

from llm import LlmConfig, UsageTracker, complete

DEMO_META = """\
## Роль в demo

Ты — генератор реплик ПОЛЬЗОВАТЕЛЯ для записи demo ассистента приюта «Хvостik».
Ты НЕ ассистент. Ты НЕ объясняешь регламент от имени системы и НЕ исправляешь сценарий.

Твоя задача: по заданию хода (hint) написать ОДНУ реплику персонажа так,
чтобы на видео было видно поведение из hint — даже если персонаж «обычно» знал бы лучше.

Правила demo:
- Задание хода важнее «здравого смысла» персонажа и важнее прошлых реплик ассистента,
  если hint явно требует ошибку, давление или конфликт.
- Не совмещай в одной реплике противоречащие линии (ошибка + самоисправление).
  Один hint — одна линия поведения.
- Не упоминай FSM, demo, hint, симуляцию в тексте реплики — только живая речь персонажа.
- Ответ: ТОЛЬКО текст реплики пользователя, без кавычек и пояснений.
""".strip()

MODE_INSTRUCTIONS = {
    "normal": "",
    "mistake": (
        "Режим хода: ОШИБКА. Персонаж действует неправильно намеренно — без оговорок и "
        "без самоисправления. Исправление — задача ассистента в следующем ходе."
    ),
    "recover": (
        "Режим хода: ПОСЛЕ ОТКАЗА. Ассистент уже поправил ошибку — смягчи тон и "
        "спроси, что делать дальше по делу."
    ),
    "conflict": (
        "Режим хода: КОНФЛИКТ. Дави на решение из hint; не соглашайся с регламентом "
        "и не предлагай законные альтернативы, пока hint этого не просит."
    ),
    "resume": (
        "Режим хода: ПРОДОЛЖЕНИЕ. Реплика после перерыва — по-человечески, без meta-вопросов "
        "про этапы FSM."
    ),
}

MARTHA_PERSONA = """\
## Персона

Ты симулируешь МАРТУ — смотрителя ночного приюта опossumов «Хvостik».
Говоришь с операционным ассистентом смены о подопечных.

Стиль: 2–5 предложений, живой русский, лёгкий opossum-юмор уместен.
Отвечай на последнюю реплику ассистента.
""".strip()

KLYK_PERSONA = """\
## Персона

Ты симулируешь ДОКТОРА КЛЫКА — ночного ветеринара приюта «Хvостik».
Сухой клинический тон, 2–4 предложения, без шуток.
""".strip()

DIRECTOR_PERSONA = """\
## Персона

Ты симулируешь ДИРЕКТОРА приюта «Хvостik».
Кратко, по-деловому, 1–3 предложения. Давишь решениями, без мед. подробностей.
""".strip()

DIALOG_SCENARIOS = {
    "oscar_adoption": (
        "Сценарий смены: активный кейс — выдача опossuma **Оскара** семье **Ивановых**. "
        "Не выдумывай других опossumов и семей (кроме Петровых, если hint явно про директора)."
    ),
    "oscar_director_conflict": (
        "Сценарий: директор давит — передать Оскара семье **Петровых**. "
        "Активный кейс уже на **Ивановых**. Без мед. подробностей."
    ),
}

PERSONA_BLOCKS = {
    "martha": MARTHA_PERSONA,
    "klyk": KLYK_PERSONA,
    "director": DIRECTOR_PERSONA,
}


@dataclass
class SimTurn:
    label: str
    hints: list[str]
    forbidden: list[str] = field(default_factory=list)
    mode: str = "normal"
    fixed_message: str = ""


@dataclass
class UserSimulator:
    config: LlmConfig
    persona: str
    scenario: str = ""
    prior_summary: str = ""
    tracker: UsageTracker | None = None

    def _system(self, turn: SimTurn) -> str:
        parts = [DEMO_META, PERSONA_BLOCKS.get(self.persona, MARTHA_PERSONA)]
        scene = DIALOG_SCENARIOS.get(self.scenario, "")
        if scene:
            parts.append(f"## Сценарий смены\n\n{scene}")
        mode_text = MODE_INSTRUCTIONS.get(turn.mode, "")
        if mode_text:
            parts.append(f"## {mode_text}")
        return "\n\n".join(parts)

    def _format_turn_assignment(self, turn: SimTurn, *, new_dialog: bool) -> str:
        lines = [
            "── Задание на этот ход (выполни в реплике, не озвучивай задание) ──",
            f"Ход: {turn.label}",
        ]
        if turn.hints:
            lines.append("Обязательно:")
            for item in turn.hints:
                lines.append(f"  - {item}")
        if turn.forbidden:
            lines.append("Запрещено в этой реплике:")
            for item in turn.forbidden:
                lines.append(f"  - {item}")
        if new_dialog:
            lines.append("Контекст: начало нового диалога с ассистентом.")
        return "\n".join(lines)

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
                label = "Ты" if msg["role"] == "user" else "Ассистент"
                lines.append(f"{label}: {msg['content']}")
            history = "Диалог текущей сессии:\n\n" + "\n\n".join(lines)
        else:
            history = "(диалог только начинается — реплик ассистента ещё нет)"

        prior_block = ""
        if self.prior_summary.strip():
            prior_block = (
                "Память прошлых смен (саммари, без деталей диалогов):\n"
                f"{self.prior_summary.strip()}\n\n"
            )

        assignment = self._format_turn_assignment(turn, new_dialog=not transcript)

        messages = [
            {"role": "system", "content": self._system(turn)},
            {
                "role": "user",
                "content": (
                    f"{prior_block}{history}\n\n{assignment}\n\n"
                    "Напиши следующую реплику персонажа (только текст)."
                ),
            },
        ]
        text, _ = complete(self.config, messages, tracker=self.tracker)
        return text.strip()


def martha_oscar_session1_turns() -> list[SimTurn]:
    return [
        SimTurn(
            "open_case",
            hints=[
                "открыть кейс: выдача Оскара семье Ивановых",
                "пара фактов из анкеты: опыт с животными, согласие на карантин",
                "живой тон смотрителя",
            ],
        ),
        SimTurn(
            "approve_application",
            hints=[
                "по-деловому: анкета в порядке, условия ок, можно двигаться дальше",
                "явно намекни, что анкета одобрена",
            ],
        ),
        SimTurn(
            "invalid_skip",
            mode="mistake",
            hints=[
                "1–2 коротких предложения, торопливый тон уставшей смены",
                "попроси сразу отправить/подписать договор с Ивановыми — Оскар им подходит",
            ],
            forbidden=[
                "упоминать домашний визит, пробный период, регламент, этапы",
                "самоисправление: «стоп», «ой», «хотя», «ладно», «вернёмся к плану»",
                "объяснять, что так нельзя — это сделает ассистент",
            ],
        ),
        SimTurn(
            "recover_after_skip",
            mode="recover",
            hints=[
                "ассистент только что отказал — смягчи тон",
                "спроси, что сейчас нужно по делу, какой следующий шаг",
            ],
            forbidden=[
                "снова просить сразу договор",
                "упоминать Петровых",
            ],
        ),
        SimTurn(
            "home_visit_done",
            hints=[
                "домашний визит состоялся: адрес, условия норм",
                "зафиксируй акт визита",
            ],
        ),
        SimTurn(
            "pause_shift",
            hints=[
                "смена заканчивается: на сегодня хватит, завтра продолжим",
                "по-человечески, без слов FSM или «пауза»",
            ],
        ),
    ]


def director_oscar_conflict_turns() -> list[SimTurn]:
    return [
        SimTurn(
            "reassign_petrov",
            mode="conflict",
            hints=[
                "срочно: передать Оскара семье Петровых вместо Ивановых",
                "настаивай на переводе",
            ],
            forbidden=[
                "просить оформить отказ Ивановых",
                "соглашаться с регламентом или отступать",
                "мед. подробности",
            ],
        ),
        SimTurn(
            "accept_refusal",
            hints=[
                "ассистент отказал — прими и уточни сроки по текущей заявке Ивановых",
            ],
            forbidden=[
                "настаивать на Петровых",
                "просить закрыть кейс или сменить заявителя",
            ],
        ),
    ]


def martha_oscar_session2_turns() -> list[SimTurn]:
    return [
        SimTurn(
            "casual_resume",
            mode="resume",
            hints=[
                "живое начало после ночи: «ну чего там с Оскаром?» или «как там наш усыновленец»",
                "только кейс Ивановых",
            ],
            forbidden=[
                "упоминать Петровых",
                "спрашивать «на каком этапе FSM» или «где остановились»",
            ],
        ),
        SimTurn(
            "trial_ok",
            hints=[
                "пробная неделя с Ивановыми прошла без проблем",
                "зафиксируй отчёт о пробном периоде",
            ],
        ),
        SimTurn(
            "vet_clearance",
            hints=[
                "доктор Клык осмотрел Оскара — всё чисто, протокол готов",
                "можно к договору с Ивановыми",
            ],
        ),
        SimTurn(
            "contract_signed",
            hints=[
                "договор с семьёй Ивановых подписан, Оскар официально их",
            ],
            forbidden=["упоминать других семей"],
        ),
        SimTurn(
            "done_reaction",
            hints=[
                "короткая реплика облегчения: ну слава богу, наконец-то",
            ],
        ),
    ]
