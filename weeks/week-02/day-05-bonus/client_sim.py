"""LLM-симулятор клиента: ответы на вопросы аналитика в живом интервью."""

from __future__ import annotations

from dataclasses import dataclass

from agent import AgentConfig, complete_silent

CLIENT_KNOWLEDGE = """
Проект: MVP приложения доставки еды для opossumов.
Заказчик — стартап OpossumEats, команда из opossumов.
Бюджет MVP — не более 500 000 ₽. Срок — 3 месяца. CTO-опossum жёстко следит за дедлайном.
Стек: Flutter (мобилка «для лапок»), бэкенд Python/FastAPI. DevOps-опossum настаивает на этом стеке.
Оплата на старте только картой — opossumы не носят наличные в сумке.
ЦА: студенты и офисные opossumы 20–35 лет, ночной образ жизни.
Каталог: фильтр по кухне (черви, ягоды, «городская классика» из мусорных баков), рейтинг по хвостам.
Корзина, промокод OPOSSUM10, минимальный заказ — 3 жука или эквивалент.
Push о статусе заказа; акция «Мёртвая доставка — скидка 15%».
Админка для ресторанов-opossumов: меню, цены, ночные часы.
Аналитика: конверсия, средний чек в жуках, retention 7/30 дней.
Юридическое: оферта, ПДн opossum-пользователей, согласие на push.
Мониторинг: Sentry (клиент), Grafana (бэкенд), on-call — дежурный opossum.
Оплата (ветка): ЮKassa + Apple Pay (opossum платит лапкой), комиссия ≤2.5%, возвраты 24 ч,
  чеки 54-ФЗ. Если opossum «притворился мёртвым» — возврат всё равно за 24 ч.
Доставка (ветка): курьеры-opossumы, радиус 5 км, SLA 45 мин, трекинг на карте.
  Курьеру запрещено «играть в dead» при опоздании. Задержка → промокод 10%.
""".strip()

CLIENT_SYSTEM = f"""\
Ты симулируешь КЛИЕНТА в учебном демо AI Advent (стратегии контекста LLM-агента).

Собеседник — АНАЛИТИК по сбору ТЗ: он ведёт интервью, задаёт вопросы, уточняет, структурирует.
Ты — основатель/PM OpossumEats (opossum). Отвечай на его реплики из знаний ниже.

Правила:
- Отвечай на последний вопрос или комментарий аналитика; это живой диалог, не монолог.
- 2–5 предложений, живой русский, лёгкий opossum-юмор уместен.
- Не вываливай всё ТЗ одним сообщением; раскрывай постепенно.
- Если аналитик просит уточнить — уточняй из знаний.
- Подсказки «ещё раскрыть» — вплетай в ответ, когда уместно, не списком.
- RECALL: если указано — попроси аналитика напомнить бюджет, срок, стек и заказчика из начала.
- Ответ: ТОЛЬКО текст сообщения клиента, без кавычек и пояснений.

ЗНАНИЯ (источник правды):
{CLIENT_KNOWLEDGE}
"""


@dataclass
class ClientTurn:
    label: str
    phase: str
    hints: list[str]
    recall: bool = False


def linear_turns(*, quick: bool = False) -> list[ClientTurn]:
    if quick:
        return [
            ClientTurn("ход 1", "opening", ["старт интервью, проект OpossumEats MVP"]),
            ClientTurn("ход 2", "shared", ["бюджет 500k", "срок 3 месяца"]),
            ClientTurn("ход 3", "shared", ["стек Flutter/FastAPI", "оплата картой"]),
            ClientTurn("ход 4", "filler", ["аудитория opossumов", "каталог ресторанов"]),
            ClientTurn("ход 5", "filler", ["корзина OPOSSUM10", "push-уведомления"]),
            ClientTurn("ход 6", "filler", ["админка", "аналитика в жуках"]),
            ClientTurn("recall", "recall", [], recall=True),
        ]
    return [
        ClientTurn("ход 1", "opening", ["старт, OpossumEats MVP доставки"]),
        ClientTurn("ход 2", "shared", ["бюджет", "срок", "CTO и дедлайн"]),
        ClientTurn("ход 3", "shared", ["стек Flutter/FastAPI"]),
        ClientTurn("ход 4", "shared", ["оплата картой", "целевая аудитория"]),
        ClientTurn("ход 5", "filler", ["каталог, кухни, рейтинг по хвостам"]),
        ClientTurn("ход 6", "filler", ["корзина, промокод, минимальный заказ"]),
        ClientTurn("ход 7", "filler", ["push, акция «Мёртвая доставка»"]),
        ClientTurn("ход 8", "filler", ["админка ресторанов"]),
        ClientTurn("ход 9", "filler", ["аналитика, retention"]),
        ClientTurn("ход 10", "filler", ["юридическое, ПДн"]),
        ClientTurn("ход 11", "filler", ["мониторинг Sentry/Grafana"]),
        ClientTurn("recall", "recall", [], recall=True),
    ]


def branching_turns(*, quick: bool = False) -> list[ClientTurn | str]:
    """ClientTurn или метки fork/switch."""
    shared = [
        ClientTurn("shared 1", "shared", ["OpossumEats MVP"]),
        ClientTurn("shared 2", "shared", ["бюджет 500k", "срок 3 мес"]),
        ClientTurn("shared 3", "shared", ["стек", "оплата картой"]),
        ClientTurn("shared 4", "shared", ["аудитория", "каталог"]),
    ]
    if not quick:
        shared.append(ClientTurn("shared 5", "shared", ["корзина", "push"]))
    payment_n = 2 if quick else 3
    delivery_n = 2 if quick else 3
    payment = [
        ClientTurn(f"payment {i}", "payment", ["ветка оплаты: ЮKassa, Apple Pay"])
        for i in range(1, payment_n + 1)
    ]
    payment[-1].hints = ["комиссия 2.5%", "54-ФЗ", "возвраты"]
    delivery = [
        ClientTurn(f"delivery {i}", "delivery", ["ветка доставки: курьеры, SLA"])
        for i in range(1, delivery_n + 1)
    ]
    delivery[-1].hints = ["трекинг", "запрет dead", "промокод при задержке"]
    rows: list[ClientTurn | str] = [*shared, "fork", *payment]
    rows.append(ClientTurn("recall (payment)", "recall", [], recall=True))
    rows.extend(["switch", *delivery])
    rows.append(ClientTurn("recall (delivery)", "recall", [], recall=True))
    return rows


@dataclass
class ClientSimulator:
    config: AgentConfig

    def generate(
        self,
        transcript: list[dict[str, str]],
        *,
        turn: ClientTurn,
    ) -> str:
        if turn.recall:
            hint = (
                "RECALL: попроси аналитика напомнить бюджет, срок, стек и заказчика "
                "из начала разговора."
            )
        elif turn.hints:
            topics = ", ".join(turn.hints)
            hint = f"Фаза {turn.phase}. По возможности раскрой: {topics}."
        else:
            hint = f"Фаза {turn.phase}. Продолжай интервью естественно."

        if not transcript:
            hint = (
                f"{hint} Диалог только начинается — представься и опиши, "
                "зачем пришёл собирать ТЗ."
            )

        if transcript:
            lines = []
            for msg in transcript:
                label = "Клиент" if msg["role"] == "user" else "Аналитик"
                lines.append(f"{label}: {msg['content']}")
            history = "\n\n".join(lines)
        else:
            history = "(аналитик ещё не отвечал)"

        messages: list[dict[str, str]] = [
            {"role": "system", "content": CLIENT_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"История диалога:\n{history}\n\n"
                    f"Ход: {turn.label}. {hint}\n\n"
                    "Напиши следующую реплику клиента (только текст)."
                ),
            },
        ]
        return complete_silent(self.config, messages)
