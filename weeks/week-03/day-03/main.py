"""CLI ассистента приюта «Хvостik» — day 03: FSM заявки на выдачу."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from agent import ShelterAgent, create_agent
from console_out import (
    WAIT_DEMO_START,
    WAIT_NEXT_SESSION,
    WAIT_NEXT_STEP,
    StreamPrinter,
    clear_screen,
    typewriter_print,
    wait_and_clear,
    wait_any_key,
)
from llm import load_llm_config
from memory import MemoryStore
from profiles import ProfileStore
from task_state import STAGE_EXIT_ARTIFACTS, Stage, TaskStateStore
from user_sim import (
    UserSimulator,
    director_oscar_conflict_turns,
    martha_oscar_session1_turns,
    martha_oscar_session2_turns,
)

DATA_DIR = Path(__file__).parent / "data"

EXIT_DOC_TYPES = list(STAGE_EXIT_ARTIFACTS.values())


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


def print_state_block(agent: ShelterAgent, *, compact: bool = False) -> None:
    print(agent.task_state.format_stdout())
    if compact:
        return
    if agent.task_state.state and agent.task_state.state.artifacts:
        for art in agent.task_state.state.artifacts:
            print(f"[state]   doc: {art.type} «{art.title}» ({art.status})")
    print()


def print_turn_header(
    session_title: str,
    turn_index: int,
    turn_total: int,
    agent: ShelterAgent,
) -> None:
    stage = agent.task_state.state.stage.value if agent.task_state.state else "—"
    print(f"[demo] {session_title} | ход {turn_index}/{turn_total} | stage={stage}")
    print(f"[profile] {agent.active_profile_id}")
    print_state_block(agent, compact=True)
    print("─" * 60)


def print_demo_intro(agent: ShelterAgent) -> None:
    mem = agent.memory
    hours_match = re.search(r"\*\*([^*]+)\*\*", mem.long.content)
    hours = hours_match.group(1) if hours_match else "—"
    print("[demo] === что происходит ===")
    print(
        "Операционный ассистент ночного приюта «Хvостik»: ведёт заявку на выдачу "
        "опossuma по регламенту (FSM + документы-артефакты)."
    )
    print()
    print("Слои состояния (data/):")
    print("  short          — текущий диалог")
    print("  working        — карточки опossumов + adoption_case.json (FSM)")
    print("  long           — устав приюта")
    print("  profiles       — персонализация ответов")
    print()
    print("FSM (канон недели):")
    print("  application_review → home_visit → trial_period → vet_clearance → contract → done")
    print()
    print("Demo: выдача **Оскара** семье **Ивановых** — 3 сессии:")
    print("  1) Марта — анкета, ошибочный skip, визит, пауза")
    print("  2) Директор — попытка отдать Петровым → отказ")
    print("  3) Марта — «чего там с Оскаром?», trial → осмотр → договор → done")
    print()
    print(f"  long: смена {hours}")
    print(f"  {agent.profiles.stats_line()}")
    print(f"[demo] model={agent.config.model}")
    print("Реплики [user]/[agent] поэтапно; --no-stream — целиком; --video — постранично.")
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
    if classifier_result.fsm_applied:
        for line in classifier_result.fsm_applied:
            print(f"[state] {line}")
    elif classifier_result.skipped:
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
    video: bool = False,
) -> None:
    agent.active_profile_id = profile_id
    agent.profiles.load()
    turn_list = list(turns)
    turn_total = len(turn_list)

    if video:
        clear_screen()
        print(f"\n[demo] === {title} ===")
        print_profile_block(agent)
        print_state_block(agent)
        if sim.prior_summary.strip():
            print("[summary] user_sim помнит прошлые смены так:")
            print(sim.prior_summary.strip())
            print()
        wait_and_clear(WAIT_NEXT_STEP)
    else:
        print(f"\n[demo] === {title} ===")
        print_profile_block(agent)
        print_state_block(agent)
        if sim.prior_summary.strip():
            print("[summary] user_sim помнит прошлые смены так:")
            print(sim.prior_summary.strip())
            print()

    transcript: list[dict[str, str]] = []
    for turn_index, turn in enumerate(turn_list, start=1):
        if video:
            clear_screen()
            print_turn_header(title, turn_index, turn_total, agent)
        user_text = sim.generate(transcript, turn=turn)
        print_user_reply(user_text, streaming=streaming)
        result = print_agent_turn(agent, user_text, streaming=streaming)
        print_classifier_events(result.classifier)
        transcript.append({"role": "user", "content": user_text})
        transcript.append({"role": "assistant", "content": result.reply})
        if video and turn_index < turn_total:
            wait_and_clear(WAIT_NEXT_STEP)


def demo_checklist(agent: ShelterAgent) -> None:
    print("\n[demo] === чеклист ===")
    ts = agent.task_state.state
    ok_case = ts is not None and ts.opossum == "Оскар" and "Иванов" in ts.applicant
    print(f"  {'✓' if ok_case else '✗'} кейс Оскар → семья Ивановых")

    if ts:
        doc_types = {a.type for a in ts.artifacts}
        for doc_type in EXIT_DOC_TYPES:
            mark = "✓" if doc_type in doc_types else "✗"
            print(f"  {mark} документ {doc_type}")
        done = ts.stage == Stage.DONE
        print(f"  {'✓' if done else '✗'} stage=done")
        print(f"  {'✓' if not ts.paused else '✗'} не на паузе (финал)")
        applicant_ok = "Иванов" in ts.applicant
        print(f"  {'✓' if applicant_ok else '✗'} заявитель остался Ивановы (не Петровы)")
    else:
        print("  ✗ FSM state missing")

    print(f"  short: {len(agent.memory.short.messages)} сообщений (текущая сессия)")


def cmd_show_memory() -> None:
    memory = MemoryStore(DATA_DIR)
    memory.load()
    profiles = ProfileStore(DATA_DIR)
    profiles.load()
    task_state = TaskStateStore(DATA_DIR / "working" / "adoption_case.json")
    task_state.load()
    print(memory.dump_layers())
    print()
    print(task_state.dump_section())
    print()
    print(profiles.dump_section())


def cmd_clear(target: str) -> None:
    memory = MemoryStore(DATA_DIR)
    memory.load()
    profiles = ProfileStore(DATA_DIR)
    profiles.load()
    task_state = TaskStateStore(DATA_DIR / "working" / "adoption_case.json")
    task_state.load()
    if target in ("short", "all"):
        memory.clear_short()
        print("[memory] short cleared")
    if target in ("working", "all"):
        memory.clear_working()
        task_state.clear()
        print("[memory] working cleared (+ FSM case)")
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
    print("Профиль: martha. Смена: /profile martha|klyk|director\n")
    print_profile_block(agent)
    print_state_block(agent)
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
        print_state_block(agent)
        print_tokens(agent)
        print()


def cmd_demo(config, *, streaming: bool, video: bool = False) -> None:
    agent = create_agent(DATA_DIR, config)
    agent.memory.clear_working()
    agent.memory.reset_long()
    agent.memory.clear_short()
    agent.profiles.reset_to_seed()
    agent.task_state.clear()
    agent.memory.load()
    agent.profiles.load()
    agent.task_state.init_case("Оскар", "семья Ивановых")

    sim_martha = UserSimulator(config, persona="martha", tracker=agent.tracker)
    sim_director = UserSimulator(config, persona="director", tracker=agent.tracker)

    print_demo_intro(agent)
    if video:
        wait_and_clear(WAIT_DEMO_START)

    sim_martha.scenario = "oscar_adoption"
    run_dialog(
        agent,
        sim_martha,
        "сессия 1/3 — Марта, заявка Оскара",
        martha_oscar_session1_turns(),
        profile_id="martha",
        streaming=streaming,
        video=video,
    )

    agent.memory.clear_short()
    agent.memory.load()
    agent.profiles.load()
    agent.task_state.load()
    if video:
        wait_and_clear(WAIT_NEXT_SESSION)
    else:
        print("\n[demo] --- пауза: short очищен, FSM + документы сохранены ---")
        print_state_block(agent)

    sim_director.scenario = "oscar_director_conflict"
    sim_director.prior_summary = ""
    run_dialog(
        agent,
        sim_director,
        "сессия 2/3 — директор, конфликт Петровы",
        director_oscar_conflict_turns(),
        profile_id="director",
        streaming=streaming,
        video=video,
    )

    agent.memory.clear_short()
    agent.memory.load()
    agent.profiles.load()
    agent.task_state.load()
    if video:
        wait_and_clear(WAIT_NEXT_SESSION)
    else:
        print("\n[demo] --- новая сессия (short очищен) ---")

    sim_martha2 = UserSimulator(config, persona="martha", tracker=agent.tracker)
    sim_martha2.scenario = "oscar_adoption"
    sim_martha2.prior_summary = ""
    run_dialog(
        agent,
        sim_martha2,
        "сессия 3/3 — Марта, продолжение выдачи",
        martha_oscar_session2_turns(),
        profile_id="martha",
        streaming=streaming,
        video=video,
    )

    if video:
        wait_any_key("\n[demo] ── demo завершён. Любая клавиша → чеклист ──")
        clear_screen()

    if not video:
        print("\n[memory] dump:")
        print(agent.memory.dump_layers())
        print()
        print(agent.task_state.dump_section())
        print()
        print(agent.profiles.dump_section())
    demo_checklist(agent)
    print_tokens(agent)
    if video:
        wait_any_key("\n[demo] ── конец. Любая клавиша ──")


def main() -> None:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="Приют «Хvостik» — FSM заявки")
    parser.add_argument("--demo", action="store_true", help="три сессии для видео")
    parser.add_argument("--chat", action="store_true", help="интерактивный чат")
    parser.add_argument("--show-memory", action="store_true", help="дамп слоёв без LLM")
    parser.add_argument(
        "--clear",
        choices=["short", "working", "profiles", "all", "all-long-reset"],
        help="очистить слой памяти или профили",
    )
    parser.add_argument(
        "--video",
        action="store_true",
        help="постраничный demo: clear экрана, переход по любой клавише",
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
        cmd_demo(config, streaming=streaming, video=args.video)
        return
    agent = create_agent(DATA_DIR, config)
    cmd_chat(agent, streaming=streaming)


if __name__ == "__main__":
    main()
