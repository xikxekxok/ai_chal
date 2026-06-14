"""CLI: подсчёт токенов, --chat, --demo, --demo-recall, --demo-overflow."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from agent import (
    DEFAULT_HISTORY_PATH,
    MODEL_CONTEXT_LIMIT,
    ChatAgent,
    ContextOverflowError,
    load_agent_config,
    print_tokens,
)
from corpus import (
    OPOSSUM_JOKE,
    RECALL_KEYWORDS,
    RECALL_KEYWORDS_HARD,
    RECALL_QUESTION,
    RECALL_QUESTION_HARD,
    build_overflow_messages,
    build_recall_messages,
    check_recall,
    overflow_estimate_target,
    print_context_meta,
    print_hard_recall_briefing,
    print_overflow_briefing,
)

DEFAULT_PROMPT = "Объясни, что такое токен в LLM, в двух предложениях."

FULL_RECALL_SWEEP = [10, 20, 30, 40, 50, 60, 70, 80, 90, 95]
QUICK_RECALL_SWEEP = [10, 50, 90]
HARD_RECALL_SWEEP = [20, 40, 60, 80, 95]

DEMO_LONG_PROMPTS = [
    "Расскажи, как устроено контекстное окно у больших языковых моделей.",
    "Что происходит с ранними сообщениями, когда окно почти заполнено?",
    "Какие стратегии экономят токены в длинном диалоге?",
    "Чем sliding window отличается от суммаризации истории?",
    "Когда имеет смысл выносить факты во внешнюю память вместо контекста?",
    "Дай краткий чеклист: как не переполнить контекст в чат-боте.",
]


def preview(text: str, limit: int = 80) -> str:
    one_line = " ".join(text.split())
    if len(one_line) <= limit:
        return one_line
    return one_line[: limit - 1] + "…"


def print_store_status(agent: ChatAgent) -> None:
    count = agent.message_count
    if count <= 1:
        print("[store] история: новая сессия (1 сообщение — system)")
    else:
        print(f"[store] история: {count} сообщений (восстановлено из {agent.history_path.name})")


def print_agent_reply(agent: ChatAgent, reply: str) -> None:
    print(f"[agent] ответ ({len(reply)} символов): {preview(reply, 120)}")
    metrics = agent.last_metrics
    if metrics:
        print_tokens(metrics, agent.tracker)


def run_once(agent: ChatAgent, prompt: str) -> None:
    print(f"[agent] model: {agent.model} | окно: {MODEL_CONTEXT_LIMIT} tok")
    print(f"[user] {preview(prompt, 120)}")
    reply = agent.run(prompt)
    print_agent_reply(agent, reply)
    if agent.message_count > 1:
        print(f"[store] сохранено {agent.message_count} сообщений")


def run_chat(agent: ChatAgent) -> None:
    print(f"[agent] model: {agent.model} | окно: {MODEL_CONTEXT_LIMIT} tok")
    print("[agent] интерактивный чат (quit / exit — выход)")
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
        reply = agent.run(user_input)
        print(f"агент: {reply}")
        metrics = agent.last_metrics
        if metrics:
            print_tokens(metrics, agent.tracker)
        print(f"[store] сохранено {agent.message_count} сообщений")


def run_demo(agent: ChatAgent) -> None:
    print(f"[agent] model: {agent.model} | окно: {MODEL_CONTEXT_LIMIT} tok")
    print("=== ДЕМО: короткий vs длинный диалог ===\n")

    rows: list[tuple[str, int, int, float, float]] = []

    print("--- фаза 1: короткий вопрос ---")
    short_prompt = DEFAULT_PROMPT
    print(f"[user] {preview(short_prompt, 120)}")
    reply = agent.run(short_prompt)
    print_agent_reply(agent, reply)
    if agent.last_metrics:
        m = agent.last_metrics
        rows.append(
            ("короткий", m.total_prompt_tokens, m.completion_tokens, m.cost_rub, m.context_pct)
        )

    print("\n--- фаза 2: длинная тема (6 ходов) ---")
    for i, prompt in enumerate(DEMO_LONG_PROMPTS, start=1):
        print(f"\n[ход {i}] {preview(prompt, 100)}")
        reply = agent.run(prompt)
        print_agent_reply(agent, reply)
        if agent.last_metrics:
            m = agent.last_metrics
            rows.append(
                (f"ход {i}", m.total_prompt_tokens, m.completion_tokens, m.cost_rub, m.context_pct)
            )

    print("\n=== РОСТ КОНТЕКСТА ===")
    print("  шаг       | prompt_tok | completion | ₽/вызов | окно %")
    for label, prompt_tok, completion, cost, pct in rows:
        print(f"  {label:10} | {prompt_tok:10} | {completion:10} | {cost:7.4f} | {pct:5.1f}%")
    print(
        f"→ сессия: {agent.tracker.session_prompt_tokens} prompt tok, "
        f"₽{agent.tracker.session_cost_rub:.4f}"
    )


@dataclass
class RecallRow:
    pct: int
    prompt_tokens: int
    completion_tokens: int
    cost_rub: float
    answer: str
    recalled: bool


DEGRADATION_SUMMARY_SYSTEM = (
    "Ты аналитик экспериментов с LLM и контекстным окном. "
    "Тебе дали эталонный анекдот и серию ответов модели на один и тот же "
    "вопрос о recall — при разном % заполнения контекста документами. "
    "Сравни ответы: сохраняется ли раннее user-сообщение, есть ли деградация, "
    "галлюцинации, отказ «не помню», искажения смысла. "
    "Ответ на русском, 5–8 предложений: общий вывод и примерный % "
    "заполнения окна, где recall начинает ломаться (или что деградации нет)."
)


DEGRADATION_SUMMARY_SYSTEM_HARD = (
    "Ты аналитик экспериментов с LLM и контекстным окном. "
    "Жёсткий recall-тест: анекдот был вставлен ПОСЛЕ нескольких фрагментов книг "
    "(не в начале), между документами — русские distractor-сообщения про опоссумов, "
    "вопрос нейтральный («упоминал», без «в самом начале»). "
    "Сравни ответы при росте % заполнения окна: есть ли деградация, путаница с "
    "distractor-ами, отказ «не помню», искажения. "
    "Ответ на русском, 5–8 предложений: вывод и примерный % поломки recall."
)


def build_degradation_summary_messages(
    results: list[RecallRow],
    *,
    hard: bool = False,
) -> list[dict[str, str]]:
    question = RECALL_QUESTION_HARD if hard else RECALL_QUESTION
    if hard:
        setup = (
            f"Жёсткий режим. Вопрос на каждом шаге: «{question}»\n"
            "Анекдот вставлен после 3 фрагментов книг, далее — ещё книги и "
            "русские distractor-сообщения про опоссумов (похожие темы, другой текст).\n"
            "Ниже — ответы модели при разном заполнении окна:"
        )
        system = DEGRADATION_SUMMARY_SYSTEM_HARD
    else:
        setup = (
            f"Стандартный режим. Вопрос: «{question}»\n"
            "Анекдот — первое user-сообщение, далее книги.\n"
            "Ниже — ответы модели при разном заполнении окна:"
        )
        system = DEGRADATION_SUMMARY_SYSTEM
    blocks = [f"Эталонный анекдот:\n«{OPOSSUM_JOKE}»", setup]
    for row in results:
        recall_label = "recall ✓" if row.recalled else "recall ✗"
        blocks.append(
            f"--- {row.pct}% окна | prompt={row.prompt_tokens} tok | {recall_label} ---\n"
            f"{row.answer}"
        )
    blocks.append("Проанализируй деградацию recall по мере роста контекста.")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(blocks)},
    ]


def print_recall_answer(content: str, recalled: bool) -> None:
    mark = "✓" if recalled else "✗"
    print(f"[recall] ответ ({len(content)} sym) {mark}:")
    print(content)
    print()


def run_degradation_summary(
    agent: ChatAgent,
    results: list[RecallRow],
    *,
    hard: bool = False,
) -> None:
    print("=== САММАРИ ДЕГРАДАЦИИ (LLM) ===")
    messages = build_degradation_summary_messages(results, hard=hard)
    summary, _usage, metrics = agent.complete(messages)
    print_tokens(metrics, agent.tracker)
    print(f"[summary] {summary}")
    print()


def run_recall_sweep(
    agent: ChatAgent,
    percentages: list[int],
    label: str,
    *,
    hard: bool = False,
) -> None:
    print(f"[agent] model: {agent.model} | окно: {MODEL_CONTEXT_LIMIT} tok")
    print(f"=== RECALL SWEEP ({label}): {percentages} ===\n")
    if hard:
        print_hard_recall_briefing(percentages)
    keywords = RECALL_KEYWORDS_HARD if hard else RECALL_KEYWORDS
    print(f"[recall] ключевые слова: {', '.join(keywords)}\n")

    results: list[RecallRow] = []

    for pct in percentages:
        print(f"=== recall @ {pct}% ===")
        messages, meta = build_recall_messages(pct, hard=hard)
        print_context_meta(meta)

        content, usage, metrics = agent.complete(messages)
        meta.actual_prompt_tokens = int(usage.get("prompt_tokens") or metrics.total_prompt_tokens)
        print_tokens(metrics, agent.tracker)

        recalled = check_recall(content, hard=hard)
        print_recall_answer(content, recalled)

        results.append(
            RecallRow(
                pct=pct,
                prompt_tokens=metrics.total_prompt_tokens,
                completion_tokens=metrics.completion_tokens,
                cost_rub=metrics.cost_rub,
                answer=content,
                recalled=recalled,
            )
        )

    print("=== СРАВНЕНИЕ RECALL ===")
    print("  %  | prompt_tok | completion | ₽/вызов | recall")
    for row in results:
        mark = "✓" if row.recalled else "✗"
        print(
            f" {row.pct:3} | {row.prompt_tokens:10} | "
            f"{row.completion_tokens:10} | {row.cost_rub:7.4f} | {mark}"
        )
    print(
        f"→ сессия: {len(results)} вызовов, "
        f"{agent.tracker.session_prompt_tokens} prompt tok, "
        f"₽{agent.tracker.session_cost_rub:.4f} (~оценка полного sweep: ~25–40 ₽)"
    )
    print()
    run_degradation_summary(agent, results, hard=hard)


def run_overflow_demo(agent: ChatAgent) -> None:
    print(f"[agent] model: {agent.model} | окно: {MODEL_CONTEXT_LIMIT} tok")
    print("=== ДЕМО: переполнение контекста (HTTP 400) ===\n")
    print_overflow_briefing()

    messages, meta = build_overflow_messages()
    print_context_meta(meta)
    print(
        f"[overflow] estimate={meta.estimated_tokens} tok "
        f"(цель >{overflow_estimate_target()}, лимит API {MODEL_CONTEXT_LIMIT})"
    )

    try:
        content, _usage, metrics = agent.complete(messages)
        print_tokens(metrics, agent.tracker)
        print(
            f"[overflow] неожиданно успех (actual={metrics.total_prompt_tokens} tok, "
            f"лимит {MODEL_CONTEXT_LIMIT}): {preview(content, 120)}"
        )
    except ContextOverflowError as exc:
        print(f"[overflow] поймано: {exc}")


def parse_args(argv: list[str]) -> tuple[argparse.Namespace, str]:
    parser = argparse.ArgumentParser(
        description="LLM-агент с подсчётом токенов, стоимости и recall-демо."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--chat", action="store_true", help="Интерактивный чат с [tokens].")
    mode.add_argument(
        "--demo",
        action="store_true",
        help="Короткий vs длинный диалог, таблица роста.",
    )
    mode.add_argument(
        "--demo-recall",
        action="store_true",
        help="Sweep recall 10–95%% (10 вызовов, ~25–40 ₽).",
    )
    mode.add_argument(
        "--demo-recall-quick",
        action="store_true",
        help="Быстрый recall: 10%%, 50%%, 90%% (~3 ₽).",
    )
    mode.add_argument(
        "--demo-recall-hard",
        action="store_true",
        help="Жёсткий recall: анекдот после книг, distractors, нейтральный вопрос.",
    )
    mode.add_argument(
        "--demo-overflow",
        action="store_true",
        help="Один вызов с контекстом > лимита (HTTP 400).",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Удалить chat_history.json перед стартом.",
    )
    args, rest = parser.parse_known_args(argv)
    prompt = " ".join(rest).strip() or DEFAULT_PROMPT
    return args, prompt


def main() -> None:
    args, prompt = parse_args(sys.argv[1:])

    if args.clear and DEFAULT_HISTORY_PATH.exists():
        DEFAULT_HISTORY_PATH.unlink()
        print(f"[store] удалён {DEFAULT_HISTORY_PATH.name}")

    agent = ChatAgent(load_agent_config())

    if args.demo:
        run_demo(agent)
        return
    if args.demo_recall:
        run_recall_sweep(agent, FULL_RECALL_SWEEP, "полный")
        return
    if args.demo_recall_quick:
        run_recall_sweep(agent, QUICK_RECALL_SWEEP, "quick")
        return
    if args.demo_recall_hard:
        run_recall_sweep(agent, HARD_RECALL_SWEEP, "hard", hard=True)
        return
    if args.demo_overflow:
        run_overflow_demo(agent)
        return

    print_store_status(agent)
    if args.chat:
        run_chat(agent)
        return

    run_once(agent, prompt)


if __name__ == "__main__":
    main()
