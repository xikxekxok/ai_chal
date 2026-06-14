"""CLI: три стратегии контекста + --demo-compare (сбор ТЗ для опоссумов)."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from agent import (
    DEFAULT_HISTORY_PATH,
    MODEL_CONTEXT_LIMIT,
    ChatAgent,
    load_agent_config,
    print_facts,
    print_strategy_stats,
    print_tokens,
)
from context import ContextConfig, StrategyKind

DEFAULT_PROMPT = "Начинаем собирать ТЗ для MVP приложения доставки еды для опоссумов."

# Сценарий: клиент диктует пункты ТЗ (агент только фиксирует, см. system prompt)
TZ_SHARED = [
    (
        "Пункт 1. Проект: MVP приложения доставки еды для опоссумов. "
        "Заказчик — стартап OpossumEats, команда тоже из опоссумов."
    ),
    (
        "Пункт 2. Бюджет MVP — не более 500 000 ₽, срок — 3 месяца. "
        "CTO-опоссум не терпит срывов дедлайна."
    ),
    "Пункт 3. Стек: Flutter (мобилка для лапок), бэкенд Python/FastAPI. DevOps-опоссум настаивает.",
    "Пункт 4. На старте только оплата картой — опossumы не носят наличные в сумке.",
    (
        "Пункт 5. Целевая аудитория — студенты-опossumы и офисные opossumы 20–35 лет, "
        "ночной образ жизни."
    ),
]

TZ_FILLER = [
    (
        "Пункт 6. Каталог ресторанов: фильтр по кухне — черви, ягоды, "
        "«городская классика» (мусорные баки). Рейтинг по звёздам и хвостам."
    ),
    (
        "Пункт 7. Корзина: несколько позиций, промокод OPOSSUM10, "
        "минимальный заказ — 3 жука или эквивалент."
    ),
    "Пункт 8. Push-уведомления о статусе заказа и акциях «Мёртвая доставка — скидка 15%».",
    "Пункт 9. Админка для ресторанов-опossumов: меню, цены, часы работы (ночь — приоритет).",
    "Пункт 10. Аналитика: конверсия, средний чек в жуках, retention за 7/30 дней.",
    "Пункт 11. Юридическое: оферта, политика ПДн для опossum-пользователей, согласие на push.",
    "Пункт 12. Мониторинг: Sentry для клиента, Grafana для бэкенда. On-call — дежурный опossum.",
]

TZ_BRANCH_PAYMENT = [
    "Пункт A1 (ветка оплаты). Интеграция с ЮKassa и Apple Pay — опossum платит лапкой.",
    (
        "Пункт A2. Комиссия платёжки не более 2.5%, возвраты за 24 часа "
        "(если opossum не притворился мёртвым)."
    ),
    "Пункт A3. Чеки 54-ФЗ через облачную кассу.",
]

TZ_BRANCH_DELIVERY = [
    "Пункт B1 (ветка доставки). Курьеры-опossumы, радиус 5 км от ресторана.",
    (
        "Пункт B2. SLA доставки — 45 минут, трекинг на карте. "
        "Курьер может «играть в dead» при опоздании — запрещено."
    ),
    "Пункт B3. При задержке — промокод 10% на следующий заказ.",
]

RECALL_QUESTION = (
    "Напомни: какой бюджет, срок и стек мы зафиксировали в начале диалога? И кто у нас заказчик?"
)
RECALL_KEYWORDS = ("500", "месяц", "flutter")

TZ_LINEAR_SCRIPT = [*TZ_SHARED, *TZ_FILLER, RECALL_QUESTION]
TZ_LINEAR_SCRIPT_QUICK = [*TZ_SHARED, *TZ_FILLER[:3], RECALL_QUESTION]


def preview(text: str, limit: int = 80) -> str:
    one_line = " ".join(text.split())
    if len(one_line) <= limit:
        return one_line
    return one_line[: limit - 1] + "…"


def check_recall(answer: str) -> bool:
    lower = answer.lower()
    return all(keyword in lower for keyword in RECALL_KEYWORDS)


def print_store_status(agent: ChatAgent) -> None:
    stats = agent.context_stats
    print(
        f"[store] стратегия={stats.strategy} | "
        f"сообщений={agent.message_count} ({agent.history_path.name})"
    )


def print_agent_reply(agent: ChatAgent, reply: str, *, full: bool = False) -> None:
    if full:
        print(f"[agent] ({len(reply)} sym):\n{reply}\n")
    else:
        print(f"[agent] ответ ({len(reply)} символов): {preview(reply, 120)}")
    print_strategy_stats(agent.context_stats)
    print_facts(agent.context_stats)
    metrics = agent.last_metrics
    if metrics:
        print_tokens(metrics, agent.tracker)


@dataclass
class CompareRow:
    turn: int
    label: str
    prompt_tokens: int
    cost_rub: float
    is_recall: bool = False


@dataclass
class CompareResult:
    label: str
    strategy: StrategyKind
    rows: list[CompareRow]
    recall_answer: str
    recalled: bool
    session_prompt_tokens: int
    session_cost_rub: float
    extra_tokens: int
    facts_count: int = 0


def run_scripted_dialogue(
    agent: ChatAgent,
    prompts: list[str],
    *,
    run_label: str,
) -> CompareResult:
    rows: list[CompareRow] = []
    recall_answer = ""

    for i, prompt in enumerate(prompts, start=1):
        is_recall = prompt == RECALL_QUESTION
        turn_label = "recall" if is_recall else f"ход {i}"
        print(f"\n[{run_label}] {turn_label}")
        print(f"[user]\n{prompt}\n")
        reply = agent.run(prompt)
        print_agent_reply(agent, reply, full=True)

        metrics = agent.last_metrics
        if metrics:
            rows.append(
                CompareRow(
                    turn=i,
                    label=turn_label,
                    prompt_tokens=metrics.total_prompt_tokens,
                    cost_rub=metrics.cost_rub,
                    is_recall=is_recall,
                )
            )
        if is_recall:
            recall_answer = reply

    stats = agent.context_stats
    return CompareResult(
        label=run_label,
        strategy=agent.strategy,
        rows=rows,
        recall_answer=recall_answer,
        recalled=check_recall(recall_answer),
        session_prompt_tokens=agent.tracker.session_prompt_tokens,
        session_cost_rub=agent.tracker.session_cost_rub,
        extra_tokens=agent.tracker.extra_prompt_tokens + agent.tracker.extra_completion_tokens,
        facts_count=stats.facts_count,
    )


def run_branching_dialogue(agent: ChatAgent, *, run_label: str) -> CompareResult:
    """Сценарий с fork: shared → payment / delivery → recall на каждой ветке."""
    rows: list[CompareRow] = []
    recall_answers: list[str] = []
    turn = 0

    def step(prompt: str, label: str) -> str:
        nonlocal turn
        turn += 1
        print(f"\n[{run_label}] {label}")
        print(f"[user]\n{prompt}\n")
        reply = agent.run(prompt)
        print_agent_reply(agent, reply, full=True)
        metrics = agent.last_metrics
        if metrics:
            rows.append(
                CompareRow(
                    turn=turn,
                    label=label,
                    prompt_tokens=metrics.total_prompt_tokens,
                    cost_rub=metrics.cost_rub,
                    is_recall=prompt == RECALL_QUESTION,
                )
            )
        return reply

    for i, prompt in enumerate(TZ_SHARED, start=1):
        step(prompt, f"shared {i}")

    print(f"\n[{run_label}] checkpoint + fork → payment, delivery")
    agent.create_checkpoint()
    agent.fork_branches("payment", "delivery")

    for i, prompt in enumerate(TZ_BRANCH_PAYMENT, start=1):
        step(prompt, f"payment {i}")
    recall_a = step(RECALL_QUESTION, "recall (payment)")
    recall_answers.append(recall_a)

    print(f"\n[{run_label}] switch → delivery")
    agent.switch_branch("delivery")
    for i, prompt in enumerate(TZ_BRANCH_DELIVERY, start=1):
        step(prompt, f"delivery {i}")
    recall_b = step(RECALL_QUESTION, "recall (delivery)")
    recall_answers.append(recall_b)

    recalled = all(check_recall(a) for a in recall_answers)
    combined_recall = recall_answers[-1]
    stats = agent.context_stats
    return CompareResult(
        label=run_label,
        strategy=agent.strategy,
        rows=rows,
        recall_answer=combined_recall,
        recalled=recalled,
        session_prompt_tokens=agent.tracker.session_prompt_tokens,
        session_cost_rub=agent.tracker.session_cost_rub,
        extra_tokens=0,
        facts_count=stats.facts_count,
    )


def print_compare_table(results: list[CompareResult]) -> None:
    print("\n=== СРАВНЕНИЕ СТРАТЕГИЙ (OpossumEats ТЗ) ===")
    print("  стратегия  | recall | prompt_tok | extra_tok | facts | ₽ сессия")
    for r in results:
        recall_mark = "✓" if r.recalled else "✗"
        extra = str(r.extra_tokens) if r.extra_tokens else "—"
        facts = str(r.facts_count) if r.facts_count else "—"
        print(
            f"  {r.label:10} | {recall_mark:6} | {r.session_prompt_tokens:10} | "
            f"{extra:9} | {facts:5} | ₽{r.session_cost_rub:.4f}"
        )

    print("\n--- recall (последний ответ) ---")
    for r in results:
        mark = "✓" if r.recalled else "✗"
        print(f"  [{r.label}] {mark}: {preview(r.recall_answer, 100)}")

    print("\n--- выводы ---")
    best_recall = [r.label for r in results if r.recalled]
    if best_recall:
        print(f"  Стабильность (recall бюджет/срок/стек): {', '.join(best_recall)}")
    else:
        print("  Стабильность: ни одна стратегия не воспроизвела все ключевые факты")

    by_tokens = sorted(results, key=lambda r: r.session_prompt_tokens)
    print(
        f"  Расход токенов: мин={by_tokens[0].label} ({by_tokens[0].session_prompt_tokens}), "
        f"макс={by_tokens[-1].label} ({by_tokens[-1].session_prompt_tokens})"
    )
    print(
        "  Удобство: sliding — просто; facts — дороже, но [facts] видно что помнит; "
        "branching — параллельные альтернативы без потери shared-контекста"
    )


def run_demo_compare(config: argparse.Namespace, *, quick: bool = False) -> None:
    window = config.window
    script = TZ_LINEAR_SCRIPT_QUICK if quick else TZ_LINEAR_SCRIPT
    mode_label = "quick" if quick else "полный"

    print(f"[agent] model: {load_agent_config().model} | окно: {MODEL_CONTEXT_LIMIT} tok")
    print(f"=== ДЕМО: сравнение стратегий ({mode_label}, window={window}) ===")
    print(
        "[demo] OpossumEats: клиент диктует пункты ТЗ по очереди, "
        "агент только фиксирует (без вопросов) → recall\n"
    )

    results: list[CompareResult] = []

    for kind, label in [
        (StrategyKind.SLIDING, "sliding"),
        (StrategyKind.FACTS, "facts"),
    ]:
        print(f"\n{'=' * 50}\n--- стратегия: {label} ---")
        agent = ChatAgent(
            load_agent_config(),
            ContextConfig(window_size=window, strategy=kind),
        )
        agent.reset_history()
        agent.tracker.reset_session()
        results.append(run_scripted_dialogue(agent, script, run_label=label))

    print(f"\n{'=' * 50}\n--- стратегия: branching ---")
    agent_branch = ChatAgent(
        load_agent_config(),
        ContextConfig(window_size=window, strategy=StrategyKind.BRANCHING),
    )
    agent_branch.reset_history()
    agent_branch.tracker.reset_session()
    results.append(run_branching_dialogue(agent_branch, run_label="branching"))

    print_compare_table(results)


def run_chat(agent: ChatAgent) -> None:
    print(f"[agent] model: {agent.model} | стратегия: {agent.strategy.value}")
    print("[agent] интерактивный чат (quit — выход)")
    if agent.strategy == StrategyKind.BRANCHING:
        print("[agent] команды: /checkpoint, /fork A B, /switch NAME")
    while True:
        try:
            user_input = input("вы: ").strip()
        except EOFError:
            print()
            break
        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit", "q"}:
            break
        if agent.strategy == StrategyKind.BRANCHING and user_input.startswith("/"):
            if user_input == "/checkpoint":
                ok = agent.create_checkpoint()
                print(f"[branch] checkpoint {'✓' if ok else '✗'}")
                print_strategy_stats(agent.context_stats)
                continue
            if user_input.startswith("/fork "):
                parts = user_input.split()
                if len(parts) == 3:
                    ok = agent.fork_branches(parts[1], parts[2])
                    print(f"[branch] fork → {parts[1]}, {parts[2]} {'✓' if ok else '✗'}")
                else:
                    print("[branch] usage: /fork name_a name_b")
                print_strategy_stats(agent.context_stats)
                continue
            if user_input.startswith("/switch "):
                name = user_input.split(maxsplit=1)[1]
                ok = agent.switch_branch(name)
                print(f"[branch] switch → {name} {'✓' if ok else '✗'}")
                print_strategy_stats(agent.context_stats)
                continue
        reply = agent.run(user_input)
        print(f"агент: {reply}")
        print_strategy_stats(agent.context_stats)
        print_facts(agent.context_stats)
        metrics = agent.last_metrics
        if metrics:
            print_tokens(metrics, agent.tracker)


def parse_args(argv: list[str]) -> tuple[argparse.Namespace, str]:
    parser = argparse.ArgumentParser(description="LLM-агент: sliding window / facts / branching.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--chat", action="store_true", help="Интерактивный чат.")
    mode.add_argument(
        "--demo-compare",
        action="store_true",
        help="Сравнение 3 стратегий на сценарии сбора ТЗ.",
    )
    mode.add_argument(
        "--demo-compare-quick",
        action="store_true",
        help="Быстрое сравнение (8 ходов + recall).",
    )
    parser.add_argument(
        "--strategy",
        choices=[s.value for s in StrategyKind],
        default=StrategyKind.SLIDING.value,
        help="Стратегия контекста (default: sliding).",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Удалить chat_history.json перед стартом.",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=6,
        metavar="N",
        help="Sliding window / facts: последние N сообщений (default: 6).",
    )
    args, rest = parser.parse_known_args(argv)
    prompt = " ".join(rest).strip() or DEFAULT_PROMPT
    return args, prompt


def main() -> None:
    args, prompt = parse_args(sys.argv[1:])
    config = load_agent_config()

    if args.demo_compare or args.demo_compare_quick:
        run_demo_compare(args, quick=args.demo_compare_quick)
        return

    context_config = ContextConfig(
        window_size=args.window,
        strategy=StrategyKind(args.strategy),
    )
    agent = ChatAgent(config, context_config)

    if args.clear:
        agent.reset_history()
        print(f"[store] удалён {DEFAULT_HISTORY_PATH.name}")

    if args.chat:
        print_store_status(agent)
        run_chat(agent)
        return

    print_store_status(agent)
    print(f"[user] {preview(prompt, 120)}")
    reply = agent.run(prompt)
    print_agent_reply(agent, reply)


if __name__ == "__main__":
    main()
