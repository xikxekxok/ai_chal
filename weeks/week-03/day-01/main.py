"""CLI ассистента приюта «Хvостik» — day 01: модель памяти."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from agent import ShelterAgent, create_agent
from llm import load_llm_config
from memory import MemoryStore, slugify
from session_summary import summarize_session
from user_sim import (
    UserSimulator,
    dialog1_turns,
    dialog2_turns,
    dialog3_turns,
)

DATA_DIR = Path(__file__).parent / "data"


def print_demo_intro(agent: ShelterAgent) -> None:
    mem = agent.memory
    hours_match = re.search(r"\*\*([^*]+)\*\*", mem.long.content)
    hours = hours_match.group(1) if hours_match else "—"
    working = mem.working.stats_line()
    print("[demo] === что происходит ===")
    print(
        "Операционный ассистент ночного приюта «Хvостik»: помогает смене "
        "с подопечными опossumами."
    )
    print()
    print("Три слоя памяти (хранятся в data/):")
    print("  short  — текущий диалог (очищается между сессиями demo)")
    print("  working — факты по каждому опossumу (JSON в data/working/)")
    print("  long   — устав приюта (data/long/charter.md)")
    print()
    print("После каждого хода LLM-классификатор решает, писать ли факты в working/long.")
    print("User_sim между диалогами видит саммари прошлых смен, не полный transcript.")
    print()
    print("Сейчас в памяти агента:")
    print(f"  long: смена {hours}, карантин 14 дней (seed charter.md)")
    print(f"  {working}")
    print(f"  {mem.short.stats_line()}")
    print()
    print("Demo: 3 отдельных диалога — приём Пушка → следующий день → директор меняет часы.")
    print(f"[demo] model={agent.config.model}")
    print()


def print_memory_event(classifier_result) -> None:
    if classifier_result.applied:
        for line in classifier_result.applied:
            print(f"[memory] classifier → {line}")
    else:
        print("[memory] classifier → skip (chat only)")


def print_tokens(agent: ShelterAgent) -> None:
    t = agent.tracker
    print(
        f"[tokens] calls={t.calls} | prompt={t.prompt_tokens} | "
        f"completion={t.completion_tokens} | ₽={t.cost_rub:.4f}"
    )


def run_dialog(
    agent: ShelterAgent,
    sim: UserSimulator,
    title: str,
    turns,
) -> str:
    print(f"\n[demo] === {title} ===")
    if sim.prior_summary.strip():
        print("[summary] user_sim помнит прошлые смены так:")
        print(sim.prior_summary.strip())
        print()
    transcript: list[dict[str, str]] = []
    for turn in turns:
        user_text = sim.generate(transcript, turn=turn)
        print(f"[user] {user_text}\n")
        result = agent.run_turn(user_text)
        print(f"[agent] {result.reply}\n")
        print_memory_event(result.classifier)
        transcript.append({"role": "user", "content": user_text})
        transcript.append({"role": "assistant", "content": result.reply})

    summary = summarize_session(
        agent.config,
        transcript,
        title,
        tracker=agent.tracker,
    )
    if summary:
        print(f"[summary] саммари «{title}» для следующих сессий:")
        print(summary)
        print()
    return summary


def demo_checklist(agent: ShelterAgent) -> None:
    print("\n[demo] === чеклист ===")
    pushok = slugify("Пушок") in agent.memory.working.opossums
    hours = "18:00" in agent.memory.long.content and "08:00" in agent.memory.long.content
    facts_count = 0
    rec = agent.memory.working.opossums.get(slugify("Пушок"), {})
    if isinstance(rec.get("facts"), dict):
        facts_count = len(rec["facts"])
    print(f"  {'✓' if pushok else '✗'} Пушок в working ({facts_count} фактов)")
    print(f"  {'✓' if hours else '✗'} новые часы 18:00–08:00 в long")
    print(f"  short: {len(agent.memory.short.messages)} сообщений (текущая сессия)")


def cmd_show_memory() -> None:
    memory = MemoryStore(DATA_DIR)
    memory.load()
    print(memory.dump_layers())


def cmd_clear(target: str) -> None:
    memory = MemoryStore(DATA_DIR)
    memory.load()
    if target in ("short", "all"):
        memory.clear_short()
        print("[memory] short cleared")
    if target in ("working", "all"):
        memory.clear_working()
        print("[memory] working cleared")
    if target == "all-long-reset":
        memory.reset_long()
        print("[memory] long reset to default charter")
    if target == "all":
        memory.reset_long()
        print("[memory] long reset to default charter")


def cmd_chat(agent: ShelterAgent) -> None:
    print("Интерактивный чат (пустая строка или /quit — выход).\n")
    while True:
        try:
            user_text = input("Вы: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_text or user_text.lower() in ("/quit", "/exit", "quit", "exit"):
            break
        result = agent.run_turn(user_text)
        print(f"\n[agent] {result.reply}\n")
        print_memory_event(result.classifier)
        print_tokens(agent)
        print()


def _append_summary(prior: str, new_part: str) -> str:
    new_part = new_part.strip()
    if not new_part:
        return prior.strip()
    if not prior.strip():
        return new_part
    return f"{prior.strip()}\n\n---\n\n{new_part}"


def cmd_demo(config) -> None:
    agent = create_agent(DATA_DIR, config)
    agent.memory.clear_working()
    agent.memory.reset_long()
    agent.memory.clear_short()
    agent.memory.load()

    sim_martha = UserSimulator(config, persona="martha", tracker=agent.tracker)
    sim_director = UserSimulator(config, persona="director", tracker=agent.tracker)

    print_demo_intro(agent)

    sim_martha.scenario = "intake"
    prior = run_dialog(agent, sim_martha, "диалог 1/3 — приём Пушка", dialog1_turns())

    print("\n[demo] --- новая сессия (short очищен, working/long сохранены) ---")
    agent.memory.clear_short()
    agent.memory.load()

    sim_martha.scenario = "next_day"
    sim_martha.prior_summary = prior
    prior = _append_summary(
        prior,
        run_dialog(agent, sim_martha, "диалог 2/3 — следующий день", dialog2_turns()),
    )

    print("\n[demo] --- новая сессия (short очищен, working/long сохранены) ---")
    agent.memory.clear_short()
    agent.memory.load()

    sim_director.scenario = "director"
    sim_director.prior_summary = prior
    run_dialog(agent, sim_director, "диалог 3/3 — директор меняет часы", dialog3_turns())

    print("\n[memory] dump:")
    print(agent.memory.dump_layers())
    demo_checklist(agent)
    print_tokens(agent)


def main() -> None:
    parser = argparse.ArgumentParser(description="Приют «Хvостik» — memory layers")
    parser.add_argument("--demo", action="store_true", help="три диалога для видео")
    parser.add_argument("--chat", action="store_true", help="интерактивный чат")
    parser.add_argument("--show-memory", action="store_true", help="дамп слоёв без LLM")
    parser.add_argument(
        "--clear",
        choices=["short", "working", "all", "all-long-reset"],
        help="очистить слой памяти",
    )
    args = parser.parse_args()

    if args.show_memory:
        cmd_show_memory()
        return
    if args.clear:
        cmd_clear(args.clear)
        return
    if not args.demo and not args.chat:
        parser.print_help()
        sys.exit(0)

    config = load_llm_config()
    if args.demo:
        cmd_demo(config)
        return
    agent = create_agent(DATA_DIR, config)
    cmd_chat(agent)


if __name__ == "__main__":
    main()
