"""Бонус: живое интервью — LLM-клиент + LLM-аналитик (тестируемый агент)."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

from agent import (
    DEFAULT_HISTORY_PATH,
    MODEL_CONTEXT_LIMIT,
    ChatAgent,
    load_agent_config,
    print_facts,
    print_strategy_stats,
    print_tokens,
)
from client_sim import ClientSimulator, ClientTurn, branching_turns, linear_turns
from context import ContextConfig, StrategyKind

RECALL_KEYWORDS = ("500", "месяц", "flutter")


def preview(text: str, limit: int = 80) -> str:
    one_line = " ".join(text.split())
    if len(one_line) <= limit:
        return one_line
    return one_line[: limit - 1] + "…"


def check_recall(answer: str) -> bool:
    lower = answer.lower()
    return all(keyword in lower for keyword in RECALL_KEYWORDS)


def print_agent_reply(agent: ChatAgent, reply: str) -> None:
    print(f"[agent] ({len(reply)} sym):\n{reply}\n")
    print_strategy_stats(agent.context_stats)
    print_facts(agent.context_stats)
    metrics = agent.last_metrics
    if metrics:
        print_tokens(metrics, agent.tracker)


@dataclass
class CompareResult:
    label: str
    strategy: StrategyKind
    recall_answer: str
    recalled: bool
    session_prompt_tokens: int
    session_cost_rub: float
    extra_tokens: int
    facts_count: int = 0
    turns: int = 0


@dataclass
class InterviewState:
    transcript: list[dict[str, str]] = field(default_factory=list)

    def append_turn(self, user: str, assistant: str) -> None:
        self.transcript.append({"role": "user", "content": user})
        self.transcript.append({"role": "assistant", "content": assistant})


def run_client_agent_turn(
    agent: ChatAgent,
    client: ClientSimulator,
    state: InterviewState,
    turn: ClientTurn,
    *,
    run_label: str,
) -> str:
    print(f"\n[{run_label}] {turn.label}")
    user_msg = client.generate(state.transcript, turn=turn)
    print(f"[client] ({len(user_msg)} sym, off-books):\n{user_msg}\n")

    reply = agent.run(user_msg)
    print_agent_reply(agent, reply)
    state.append_turn(user_msg, reply)
    return reply


def run_linear_interview(
    agent: ChatAgent,
    client: ClientSimulator,
    *,
    run_label: str,
    quick: bool = False,
) -> CompareResult:
    state = InterviewState()
    turns = linear_turns(quick=quick)
    recall_answer = ""

    for turn in turns:
        reply = run_client_agent_turn(agent, client, state, turn, run_label=run_label)
        if turn.recall:
            recall_answer = reply

    stats = agent.context_stats
    return CompareResult(
        label=run_label,
        strategy=agent.strategy,
        recall_answer=recall_answer,
        recalled=check_recall(recall_answer),
        session_prompt_tokens=agent.tracker.session_prompt_tokens,
        session_cost_rub=agent.tracker.session_cost_rub,
        extra_tokens=agent.tracker.extra_prompt_tokens + agent.tracker.extra_completion_tokens,
        facts_count=stats.facts_count,
        turns=len(turns),
    )


def run_branching_interview(
    agent: ChatAgent,
    client: ClientSimulator,
    *,
    run_label: str,
    quick: bool = False,
) -> CompareResult:
    state = InterviewState()
    plan = branching_turns(quick=quick)
    recall_answers: list[str] = []
    client_turns = 0

    for item in plan:
        if item == "fork":
            print(f"\n[{run_label}] checkpoint + fork → payment, delivery")
            agent.create_checkpoint()
            agent.fork_branches("payment", "delivery")
            continue
        if item == "switch":
            print(f"\n[{run_label}] switch → delivery")
            agent.switch_branch("delivery")
            continue

        assert isinstance(item, ClientTurn)
        client_turns += 1
        reply = run_client_agent_turn(agent, client, state, item, run_label=run_label)
        if item.recall:
            recall_answers.append(reply)

    stats = agent.context_stats
    return CompareResult(
        label=run_label,
        strategy=agent.strategy,
        recall_answer=recall_answers[-1] if recall_answers else "",
        recalled=all(check_recall(a) for a in recall_answers),
        session_prompt_tokens=agent.tracker.session_prompt_tokens,
        session_cost_rub=agent.tracker.session_cost_rub,
        extra_tokens=0,
        facts_count=stats.facts_count,
        turns=client_turns,
    )


def print_compare_table(results: list[CompareResult]) -> None:
    print("\n=== СРАВНЕНИЕ (интервью LLM+LLM, OpossumEats) ===")
    print("  стратегия  | recall | prompt_tok | extra_tok | facts | ₽ сессия | ходов")
    for r in results:
        recall_mark = "✓" if r.recalled else "✗"
        extra = str(r.extra_tokens) if r.extra_tokens else "—"
        facts = str(r.facts_count) if r.facts_count else "—"
        print(
            f"  {r.label:10} | {recall_mark:6} | {r.session_prompt_tokens:10} | "
            f"{extra:9} | {facts:5} | ₽{r.session_cost_rub:.4f} | {r.turns}"
        )

    print("\n--- recall ---")
    for r in results:
        mark = "✓" if r.recalled else "✗"
        print(f"  [{r.label}] {mark}: {preview(r.recall_answer, 100)}")

    print("\n--- выводы ---")
    best = [r.label for r in results if r.recalled]
    if best:
        print(f"  Recall: {', '.join(best)}")
    by_tokens = sorted(results, key=lambda r: r.session_prompt_tokens)
    print(
        f"  Токены агента-аналитика: мин={by_tokens[0].label}, макс={by_tokens[-1].label} "
        "(client LLM off-books)"
    )


def run_demo_compare(config: argparse.Namespace, *, quick: bool = False) -> None:
    window = config.window
    mode_label = "quick" if quick else "полный"
    cfg = load_agent_config()

    print(f"[agent] model: {cfg.model} | окно: {MODEL_CONTEXT_LIMIT} tok")
    print(f"=== БОНУС: интервью LLM+LLM ({mode_label}, window={window}) ===")
    print(
        "[demo] Аналитик (агент) ведёт интервью, клиент (LLM) отвечает на вопросы. "
        "[client] off-books. day-05 — скрипт; bonus — живой диалог.\n"
    )

    client = ClientSimulator(cfg)
    results: list[CompareResult] = []

    for kind, label in [
        (StrategyKind.SLIDING, "sliding"),
        (StrategyKind.FACTS, "facts"),
    ]:
        print(f"\n{'=' * 50}\n--- стратегия: {label} ---")
        agent = ChatAgent(cfg, ContextConfig(window_size=window, strategy=kind))
        agent.reset_history()
        agent.tracker.reset_session()
        results.append(run_linear_interview(agent, client, run_label=label, quick=quick))

    print(f"\n{'=' * 50}\n--- стратегия: branching ---")
    agent_branch = ChatAgent(
        cfg, ContextConfig(window_size=window, strategy=StrategyKind.BRANCHING)
    )
    agent_branch.reset_history()
    agent_branch.tracker.reset_session()
    results.append(
        run_branching_interview(agent_branch, client, run_label="branching", quick=quick)
    )

    print_compare_table(results)


def run_single_interview(
    agent: ChatAgent,
    client: ClientSimulator,
    *,
    quick: bool = False,
) -> None:
    if agent.strategy == StrategyKind.BRANCHING:
        run_branching_interview(agent, client, run_label=agent.strategy.value, quick=quick)
    else:
        run_linear_interview(agent, client, run_label=agent.strategy.value, quick=quick)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Бонус day-05: интервью LLM-клиент + аналитик, context strategies."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--demo-compare", action="store_true")
    mode.add_argument("--demo-compare-quick", action="store_true")
    mode.add_argument("--interview", action="store_true")
    parser.add_argument(
        "--strategy",
        choices=[s.value for s in StrategyKind],
        default=StrategyKind.SLIDING.value,
    )
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--window", type=int, default=6, metavar="N")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv[1:])
    cfg = load_agent_config()

    if args.demo_compare or args.demo_compare_quick:
        run_demo_compare(args, quick=args.demo_compare_quick)
        return

    context_config = ContextConfig(
        window_size=args.window,
        strategy=StrategyKind(args.strategy),
    )
    agent = ChatAgent(cfg, context_config)
    client = ClientSimulator(cfg)

    if args.clear:
        agent.reset_history()
        print(f"[store] удалён {DEFAULT_HISTORY_PATH.name}")

    if args.interview:
        print(f"[agent] аналитик | стратегия: {agent.strategy.value} | LLM-клиент: on")
        run_single_interview(agent, client, quick=False)
        return

    print("Режимы: --demo-compare | --demo-compare-quick | --interview --strategy …")
    sys.exit(1)


if __name__ == "__main__":
    main()
