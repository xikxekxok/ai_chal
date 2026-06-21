"""CLI ассистента приюта «Хvостik» — day 02: персонализация."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from agent import ShelterAgent, create_agent
from console_out import StreamPrinter, typewriter_print
from llm import load_llm_config
from memory import MemoryStore, slugify
from profiles import ProfileStore
from session_summary import summarize_session
from user_sim import (
    UserSimulator,
    director_lapka_turns,
    klyk_lapka_turns,
    martha_lapka_turns,
)

DATA_DIR = Path(__file__).parent / "data"


def _ensure_utf8_stdout() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass


def print_profile_block(agent: ShelterAgent) -> None:
    profile = agent.profiles.get(agent.active_profile_id)
    if profile is None:
        print("[profile] (профиль не найден)")
        return
    print("[profile] активный собеседник:")
    print(agent.profiles.format_profile_stdout(profile))
    print()


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
    print("Слои состояния (хранятся в data/):")
    print("  short    — текущий диалог (очищается между сессиями demo)")
    print("  working  — факты по каждому опossumу (JSON в data/working/)")
    print("  long     — устав приюта (data/long/charter.md)")
    print("  profiles — персонализация (стиль, формат, constraints, learned)")
    print()
    print("Профиль подмешивается в каждый запрос. Классификатор может дописать learned.")
    print("Между сессиями demo short очищается; working, long и profiles сохраняются.")
    print()
    print("Сейчас в памяти агента:")
    print(f"  long: смена {hours}, карантин 14 дней (seed charter.md)")
    print(f"  {working}")
    print(f"  {mem.short.stats_line()}")
    print(f"  {agent.profiles.stats_line()}")
    print()
    print(
        "Demo: 3 сессии с разными профилями — "
        "Марта (приём Лапки) → доктор Клык (протокол) → директор (статус)."
    )
    print(f"[demo] model={agent.config.model}")
    print("Реплики [user]/[agent] печатаются поэтапно; --no-stream — целиком.")
    print()


def print_user_reply(user_text: str, *, streaming: bool) -> None:
    if streaming:
        typewriter_print("[user] ", user_text)
    else:
        print(f"[user] {user_text}\n")


def print_agent_turn(agent: ShelterAgent, user_text: str, *, streaming: bool):
    if streaming:
        printer = StreamPrinter("[agent] ")
        result = agent.run_turn(user_text, stream=True, on_delta=printer.on_delta)
        printer.finish()
    else:
        result = agent.run_turn(user_text, stream=False)
        print(f"[agent] {result.reply}\n")
    return result

def print_classifier_events(classifier_result) -> None:
    if classifier_result.applied:
        for line in classifier_result.applied:
            print(f"[memory] classifier → {line}")
    if classifier_result.profile_applied:
        for line in classifier_result.profile_applied:
            print(f"[profile] classifier → {line}")
    if classifier_result.skipped:
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
    *,
    profile_id: str,
    streaming: bool,
) -> str:
    agent.active_profile_id = profile_id
    agent.profiles.load()
    print(f"\n[demo] === {title} ===")
    print_profile_block(agent)
    if sim.prior_summary.strip():
        print("[summary] user_sim помнит прошлые смены так:")
        print(sim.prior_summary.strip())
        print()
    transcript: list[dict[str, str]] = []
    for turn in turns:
        user_text = sim.generate(transcript, turn=turn)
        print_user_reply(user_text, streaming=streaming)
        result = print_agent_turn(agent, user_text, streaming=streaming)
        print_classifier_events(result.classifier)
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
    lapka = slugify("Лапка") in agent.memory.working.opossums
    facts_count = 0
    rec = agent.memory.working.opossums.get(slugify("Лапка"), {})
    if isinstance(rec.get("facts"), dict):
        facts_count = len(rec["facts"])
    print(f"  {'✓' if lapka else '✗'} Лапка в working ({facts_count} фактов)")

    all_learned = True
    for profile in agent.profiles.all():
        ok = len(profile.learned) >= 1
        all_learned = all_learned and ok
        mark = "✓" if ok else "✗"
        keys = ", ".join(profile.learned) if profile.learned else "—"
        print(f"  {mark} profile {profile.id}: learned ({keys})")

    styles = {p.id: p.style for p in agent.profiles.all()}
    distinct = len(set(styles.values())) == len(styles) and len(styles) >= 3
    print(f"  {'✓' if distinct else '✗'} seed-профили различаются по стилю")
    print(f"  short: {len(agent.memory.short.messages)} сообщений (текущая сессия)")


def cmd_show_memory() -> None:
    memory = MemoryStore(DATA_DIR)
    memory.load()
    profiles = ProfileStore(DATA_DIR)
    profiles.load()
    print(memory.dump_layers())
    print()
    print(profiles.dump_section())


def cmd_clear(target: str) -> None:
    memory = MemoryStore(DATA_DIR)
    memory.load()
    profiles = ProfileStore(DATA_DIR)
    profiles.load()
    if target in ("short", "all"):
        memory.clear_short()
        print("[memory] short cleared")
    if target in ("working", "all"):
        memory.clear_working()
        print("[memory] working cleared")
    if target in ("profiles", "all"):
        profiles.reset_to_seed()
        print("[profile] profiles reset to seed")
    if target == "all-long-reset":
        memory.reset_long()
        print("[memory] long reset to default charter")
    if target == "all":
        memory.reset_long()
        print("[memory] long reset to default charter")


def cmd_chat(agent: ShelterAgent, *, streaming: bool) -> None:
    print("Интерактивный чат (пустая строка или /quit — выход).")
    print("Профиль по умолчанию: martha. Смена: /profile martha|klyk|director\n")
    print_profile_block(agent)
    while True:
        try:
            user_text = input("Вы: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_text:
            break
        lower = user_text.lower()
        if lower in ("/quit", "/exit", "quit", "exit"):
            break
        if lower.startswith("/profile "):
            profile_id = user_text.split(maxsplit=1)[1].strip().lower()
            if agent.profiles.get(profile_id):
                agent.active_profile_id = profile_id
                print(f"\n[profile] переключено на {profile_id}")
                print_profile_block(agent)
            else:
                print(f"\n[profile] неизвестный профиль: {profile_id}")
            continue
        print()
        result = print_agent_turn(agent, user_text, streaming=streaming)
        print_classifier_events(result.classifier)
        print_tokens(agent)
        print()


def cmd_demo(config, *, streaming: bool) -> None:
    agent = create_agent(DATA_DIR, config)
    agent.memory.clear_working()
    agent.memory.reset_long()
    agent.memory.clear_short()
    agent.profiles.reset_to_seed()
    agent.memory.load()
    agent.profiles.load()

    sim_martha = UserSimulator(config, persona="martha", tracker=agent.tracker)
    sim_klyk = UserSimulator(config, persona="klyk", tracker=agent.tracker)
    sim_director = UserSimulator(config, persona="director", tracker=agent.tracker)

    print_demo_intro(agent)

    sim_martha.scenario = "lapka_intake"
    run_dialog(
        agent,
        sim_martha,
        "сессия 1/3 — Марта, приём Лапки",
        martha_lapka_turns(),
        profile_id="martha",
        streaming=streaming,
    )

    print("\n[demo] --- новая сессия (short очищен, working/long/profiles сохранены) ---")
    agent.memory.clear_short()
    agent.memory.load()
    agent.profiles.load()

    sim_klyk.scenario = "lapka_vet"
    sim_klyk.prior_summary = ""
    run_dialog(
        agent,
        sim_klyk,
        "сессия 2/3 — доктор Клык, протокол",
        klyk_lapka_turns(),
        profile_id="klyk",
        streaming=streaming,
    )

    print("\n[demo] --- новая сессия (short очищен, working/long/profiles сохранены) ---")
    agent.memory.clear_short()
    agent.memory.load()
    agent.profiles.load()

    sim_director.scenario = "lapka_director"
    sim_director.prior_summary = ""
    run_dialog(
        agent,
        sim_director,
        "сессия 3/3 — директор, статус",
        director_lapka_turns(),
        profile_id="director",
        streaming=streaming,
    )

    print("\n[memory] dump:")
    print(agent.memory.dump_layers())
    print()
    print(agent.profiles.dump_section())
    demo_checklist(agent)
    print_tokens(agent)


def main() -> None:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="Приют «Хvостik» — персонализация")
    parser.add_argument("--demo", action="store_true", help="три сессии для видео")
    parser.add_argument("--chat", action="store_true", help="интерактивный чат")
    parser.add_argument("--show-memory", action="store_true", help="дамп слоёв без LLM")
    parser.add_argument(
        "--clear",
        choices=["short", "working", "profiles", "all", "all-long-reset"],
        help="очистить слой памяти или профили",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="печатать реплики целиком, без поэтапного вывода",
    )
    args = parser.parse_args()
    streaming = not args.no_stream

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
        cmd_demo(config, streaming=streaming)
        return
    agent = create_agent(DATA_DIR, config)
    cmd_chat(agent, streaming=streaming)


if __name__ == "__main__":
    main()
