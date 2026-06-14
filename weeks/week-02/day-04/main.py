"""CLI: сжатие истории, --chat, --demo-compare (диалог про опоссумов)."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from agent import (
    DEFAULT_HISTORY_PATH,
    MODEL_CONTEXT_LIMIT,
    ChatAgent,
    load_agent_config,
    print_compress,
    print_summary_created,
    print_tokens,
)
from context import CompressionConfig

DEFAULT_PROMPT = "Расскажи одним предложением, чем опоссум отличается от енота."

OPOSSUM_JOKE = (
    "Почему опоссум не играет в прятки? — Потому что когда его находят, "
    "он притворяется мёртвым, а потом всё равно проигрывает: "
    "он ведь не прятался, он «устал»."
)
JOKE_USER_MSG = f"Кстати, анекдот про опоссумов: «{OPOSSUM_JOKE}»"
RECALL_QUESTION = "Какой анекдот про опоссумов я писал в самом начале?"
RECALL_KEYWORDS = ("опоссум", "прятки", "притворяется")

OPOSSUM_CHAT_PROMPTS = [
    JOKE_USER_MSG,
    "Где живут опоссумы и чем они отличаются от других сумчатых?",
    "Что такое игра dead у опоссума при опасности?",
    "Сколько зубов у опоссума и зачем так много?",
    "Опоссумы активны днём или ночью?",
    "Может ли опоссум висеть на хвосте?",
    "Чем питаются опоссумы в городе?",
    "Как долго живут опоссумы в дикой природе?",
    "Есть ли опоссумы в России?",
    "Почему опоссумов иногда называют перхотными?",
    "Как опоссумы переносят холод зимой?",
    "Чем опасен опоссум для домашних животных?",
]

OPOSSUM_CHAT_PROMPTS_QUICK = OPOSSUM_CHAT_PROMPTS[:7]


def preview(text: str, limit: int = 80) -> str:
    one_line = " ".join(text.split())
    if len(one_line) <= limit:
        return one_line
    return one_line[: limit - 1] + "…"


def check_recall(answer: str) -> bool:
    lower = answer.lower()
    return all(keyword in lower for keyword in RECALL_KEYWORDS)


def print_store_status(agent: ChatAgent) -> None:
    count = agent.message_count
    mode = "сжатие вкл" if agent.compression_enabled else "сжатие выкл"
    if count <= 1:
        print(f"[store] история: новая сессия (system) | {mode}")
    else:
        print(
            f"[store] история: {count} сообщений "
            f"({agent.history_path.name}) | {mode}"
        )


def print_agent_reply(agent: ChatAgent, reply: str, *, full: bool = False) -> None:
    if full:
        print(f"[agent] ({len(reply)} sym):\n{reply}\n")
    else:
        print(f"[agent] ответ ({len(reply)} символов): {preview(reply, 120)}")
    if full:
        if summary := agent.drain_summary_created():
            print_summary_created(summary)
    metrics = agent.last_metrics
    if metrics:
        print_tokens(metrics, agent.tracker)
    if agent.compression_enabled:
        print_compress(agent.compression_stats)


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
        if summary := agent.drain_summary_created():
            print_summary_created(summary)
        metrics = agent.last_metrics
        if metrics:
            print_tokens(metrics, agent.tracker)
        if agent.compression_enabled:
            print_compress(agent.compression_stats)
        print(f"[store] сохранено {agent.message_count} сообщений")


@dataclass
class CompareRow:
    turn: int
    label: str
    prompt_tokens: int
    cost_rub: float
    is_recall: bool = False
    recalled: bool | None = None


@dataclass
class CompareResult:
    label: str
    rows: list[CompareRow]
    recall_answer: str
    recalled: bool
    session_prompt_tokens: int
    session_cost_rub: float
    summarize_prompt_tokens: int
    compress_events: int


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

    recalled = check_recall(recall_answer)
    stats = agent.compression_stats
    return CompareResult(
        label=run_label,
        rows=rows,
        recall_answer=recall_answer,
        recalled=recalled,
        session_prompt_tokens=agent.tracker.session_prompt_tokens,
        session_cost_rub=agent.tracker.session_cost_rub,
        summarize_prompt_tokens=stats.summarize_prompt_tokens,
        compress_events=stats.compress_events,
    )


def print_compare_table(without: CompareResult, with_compress: CompareResult) -> None:
    print("\n=== СРАВНЕНИЕ СЖАТИЯ (диалог про опоссумов) ===")
    print("  режим      | ход    | prompt_tok | ₽/ход  | recall")
    for row in without.rows:
        recall_col = ""
        if row.is_recall:
            mark = "✓" if without.recalled else "✗"
            recall_col = mark
        print(
            f"  {'без':10} | {row.label:6} | {row.prompt_tokens:10} | "
            f"{row.cost_rub:6.4f} | {recall_col}"
        )
    for row in with_compress.rows:
        recall_col = ""
        if row.is_recall:
            mark = "✓" if with_compress.recalled else "✗"
            recall_col = mark
        print(
            f"  {'сжатие':10} | {row.label:6} | {row.prompt_tokens:10} | "
            f"{row.cost_rub:6.4f} | {recall_col}"
        )

    print(
        f"\n→ без сжатия: {without.session_prompt_tokens} prompt tok, "
        f"₽{without.session_cost_rub:.4f}, recall "
        f"{'✓' if without.recalled else '✗'}"
    )
    print(
        f"→ со сжатием: {with_compress.session_prompt_tokens} prompt tok "
        f"(+{with_compress.summarize_prompt_tokens} на summarize), "
        f"₽{with_compress.session_cost_rub:.4f}, "
        f"сжатий={with_compress.compress_events}, recall "
        f"{'✓' if with_compress.recalled else '✗'}"
    )

    saved = without.session_prompt_tokens - with_compress.session_prompt_tokens
    if saved > 0:
        pct = saved / without.session_prompt_tokens * 100
        print(f"→ экономия prompt tok: {saved} ({pct:.0f}%)")


def run_demo_compare(
    config: argparse.Namespace,
    *,
    quick: bool = False,
) -> None:
    chat_prompts = OPOSSUM_CHAT_PROMPTS_QUICK if quick else OPOSSUM_CHAT_PROMPTS
    script = [*chat_prompts, RECALL_QUESTION]
    keep = config.keep
    compress_every = config.compress_every

    mode_label = "quick" if quick else "полный"
    print(f"[agent] model: {load_agent_config().model} | окно: {MODEL_CONTEXT_LIMIT} tok")
    print(f"=== ДЕМО: сравнение сжатия ({mode_label}, {len(script)} ходов) ===")
    print("[demo] сценарий: разговор про опоссумов + recall анекдота")
    print(f"[demo] keep_recent={keep}, compress_every={compress_every}\n")

    print("--- фаза A: без сжатия ---")
    agent_plain = ChatAgent(
        load_agent_config(),
        compression=CompressionConfig(
            keep_recent=keep,
            compress_every=compress_every,
            enabled=False,
        ),
    )
    agent_plain.reset_history()
    agent_plain.tracker.reset_session()
    without = run_scripted_dialogue(agent_plain, script, run_label="без")

    print("\n--- фаза B: со сжатием ---")
    agent_compressed = ChatAgent(
        load_agent_config(),
        compression=CompressionConfig(
            keep_recent=keep,
            compress_every=compress_every,
            enabled=True,
        ),
    )
    agent_compressed.reset_history()
    agent_compressed.tracker.reset_session()
    with_compress = run_scripted_dialogue(
        agent_compressed, script, run_label="сжатие"
    )

    print_compare_table(without, with_compress)


def parse_args(argv: list[str]) -> tuple[argparse.Namespace, str]:
    parser = argparse.ArgumentParser(
        description="LLM-агент со сжатием истории (summary + последние N сообщений)."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--chat", action="store_true", help="Интерактивный чат.")
    mode.add_argument(
        "--demo-compare",
        action="store_true",
        help="Сравнение с/без сжатия: диалог про опоссумов + recall.",
    )
    mode.add_argument(
        "--demo-compare-quick",
        action="store_true",
        help="Быстрое сравнение (7 ходов + recall, ~1 ₽).",
    )
    parser.add_argument(
        "--no-compress",
        action="store_true",
        help="Отключить сжатие (one-shot / --chat).",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Удалить chat_history.json перед стартом.",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=6,
        metavar="N",
        help="Последние N сообщений без сжатия (default: 6).",
    )
    parser.add_argument(
        "--compress-every",
        type=int,
        default=10,
        metavar="N",
        help="Сжимать каждые N архивных сообщений (default: 10).",
    )
    args, rest = parser.parse_known_args(argv)
    prompt = " ".join(rest).strip() or DEFAULT_PROMPT
    return args, prompt


def main() -> None:
    args, prompt = parse_args(sys.argv[1:])
    config = load_agent_config()

    compression = CompressionConfig(
        keep_recent=args.keep,
        compress_every=args.compress_every,
        enabled=not args.no_compress,
    )

    if args.demo_compare or args.demo_compare_quick:
        run_demo_compare(args, quick=args.demo_compare_quick)
        return

    agent = ChatAgent(config, compression=compression)

    if args.clear:
        agent.reset_history()
        print(f"[store] удалён {DEFAULT_HISTORY_PATH.name}")

    if args.chat:
        print_store_status(agent)
        run_chat(agent)
        return

    print_store_status(agent)
    run_once(agent, prompt)


if __name__ == "__main__":
    main()
