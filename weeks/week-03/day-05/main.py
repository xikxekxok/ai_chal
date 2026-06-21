"""CLI ассистента приюта «Хvostik» — day 05: TikTok FSM + controlled transitions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agent import ShelterAgent, TurnResult, create_agent
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
from invariants import InvariantStore
from llm import load_llm_config
from memory import MemoryStore
from profiles import ProfileStore
from session_summary import summarize_session
from task_state import TIKTOK_CASE_FILE, Stage, TaskStateStore
from user_sim import (
    SimTurn,
    UserSimulator,
    sasha_demo_session1_turns,
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
    turn_total: int | None,
    agent: ShelterAgent,
) -> None:
    stage = agent.task_state.state.stage.value if agent.task_state.state else "—"
    if turn_total is None:
        turn_label = f"ход {turn_index}"
    else:
        turn_label = f"ход {turn_index}/{turn_total}"
    print(f"[demo] {session_title} | {turn_label} | stage={stage}")
    print(f"[profile] {agent.active_profile_id}")
    print_state_block(agent, compact=True)
    print("─" * 60)


def print_demo_intro(agent: ShelterAgent) -> None:
    print("[demo] === что происходит ===")
    print()
    print(
        "После того, как Марта переела на помойке свежих фруктов и сошла с ума, "
        "руководство проанализировало её безумие и **одобрило** использование "
        "подопечных для снятия TikTok — разумеется, исключительно чтобы пополнять "
        "скудный бюджет приюта."
    )
    print()
    print(
        "Молодому волонтёру **Саше** поручили осваивать этот нелёгкий способ заработка... "
    )
    print()
    print("Тема дня: **контролируемые переходы** FSM «Хvostik Clips».")
    print("  pitch → welfare_check → rehearsal → publish → done")
    print("  Переход делает **волонтёр**; FSM ограничивает **ассистента**.")
    print()
    print("Слои состояния (data/):")
    print("  short                    — текущий диалог")
    print("  working/tiktok_shoot.json — FSM съёмки")
    print("  long/tiktok_regulation.md — регламент Clips")
    print("  long/invariants.json     — инварианты")
    print("  profiles                 — персонализация (demo: sasha)")
    print()
    print("Demo: Саша **настойчиво** добивается ролика — первый ход «щас на телефон сниму»")
    print("  (нарушение); в промпте Саши — первый бриф **без длительности**, потом fix.")
    print("  5 ходов → пауза → до stage=done.")
    print("  Demo: [user] → [classifier/transition] → [agent]; FSM до ответа агента.")
    print()
    print(f"  {agent.invariants.stats_line()}")
    print(f"  {agent.profiles.stats_line()}")
    print(f"[demo] model={agent.config.model}")
    print("Реплики [user]/[agent] поэтапно; --no-stream — целиком; --video — постранично.")
    print()


def print_user_reply(user_text: str, *, streaming: bool) -> None:
    if streaming:
        typewriter_print("[user] ", user_text)
    else:
        print(f"[user] {user_text}\n")


def print_invariant_block(result: TurnResult) -> None:
    if result.validation_skipped:
        return
    dv = result.draft_validation
    fv = result.final_validation
    if dv is None:
        return
    if result.retried:
        if fv and fv.pass_:
            print("[invariant] retry → pass")
        elif fv and not fv.pass_:
            print("[invariant] ✗ retry STILL FAILING")
    elif dv.pass_:
        print("[invariant] pass")


def print_agent_turn(
    agent: ShelterAgent,
    user_text: str,
    *,
    streaming: bool,
    skip_validation: bool = False,
    skip_profile_updates: bool = False,
) -> TurnResult:
    if streaming:
        print_classifier_events_placeholder = print_classifier_events

        def on_classifier(classifier_result) -> None:
            print_classifier_events_placeholder(classifier_result)
            print()

        printer = StreamPrinter("[agent] ")
        result = agent.run_turn(
            user_text,
            stream=True,
            on_delta=printer.on_delta,
            skip_validation=skip_validation,
            skip_profile_updates=skip_profile_updates,
            on_classifier_done=on_classifier,
        )
        printer.finish()
        print_invariant_block(result)
    else:
        result = agent.run_turn(
            user_text,
            stream=False,
            skip_validation=skip_validation,
            skip_profile_updates=skip_profile_updates,
        )
        print_classifier_events(result.classifier)
        print(f"[agent] {result.final_reply}\n")
        print_invariant_block(result)
    return result


def _classifier_intent_line(classifier_result) -> str:
    fsm = classifier_result.fsm
    raw = classifier_result.raw.strip()
    suffix = ""
    if not fsm and raw and "{" not in raw[:100]:
        suffix = " | ⚠ ответ не JSON"
    if not fsm:
        return f"fsm=null{suffix}"
    event = str(fsm.get("event") or "?").strip()
    parts = [f"event={event}"]
    if event == "complete_stage":
        parts.append("user closes stage")
    elif event == "advance":
        target = fsm.get("target_stage")
        if target:
            parts.append(f"target={target}")
    elif event == "update_step":
        step = fsm.get("step")
        if step:
            parts.append(f"step={step!r}")
    return " | ".join(parts) + suffix


def print_classifier_events(classifier_result) -> None:
    intent = _classifier_intent_line(classifier_result)
    saves_n = len(classifier_result.saves)
    if saves_n:
        print(f"[classifier] {intent} | saves={saves_n}")
    else:
        print(f"[classifier] {intent}")

    fsm = classifier_result.fsm or {}
    event = str(fsm.get("event", "")).lower()
    if event == "complete_stage":
        denied = [ln for ln in classifier_result.fsm_applied if ln.startswith("denied complete")]
        if denied:
            reason = denied[0].removeprefix("denied complete: ")
            print(f"[classifier] → код отклонил переход: {reason}")

    if classifier_result.applied:
        for line in classifier_result.applied:
            print(f"[memory] classifier → {line}")
    if classifier_result.profile_applied:
        for line in classifier_result.profile_applied:
            print(f"[profile] classifier → {line}")
    if classifier_result.fsm_applied:
        for line in classifier_result.fsm_applied:
            if line.startswith("allowed ") or line.startswith("denied "):
                print(f"[transition] {line}")
            else:
                print(f"[state] {line}")
    elif classifier_result.skipped:
        print("[classifier] (ничего не применено)")


def build_user_sim_resume(
    agent: ShelterAgent,
    transcript: list[dict[str, str]],
    session_title: str,
) -> str:
    """Саммари прошлой смены + FSM + хвост диалога для user_sim после clear short."""
    parts: list[str] = []
    summary = summarize_session(
        agent.config,
        transcript,
        session_title,
        tracker=agent.tracker,
    )
    if summary:
        parts.append(summary)
    state = agent.task_state.state
    if state:
        parts.append(
            f"Кейс TikTok с {state.opossum}: сейчас этап **{state.stage.value}** "
            f"({state.step}). Смена продолжается после паузы — не начинай pitch заново."
        )
    if transcript:
        last_user = next(
            (m["content"] for m in reversed(transcript) if m["role"] == "user"),
            "",
        )
        last_asst = next(
            (m["content"] for m in reversed(transcript) if m["role"] == "assistant"),
            "",
        )
        if last_user or last_asst:
            parts.append(
                "Последний обмен прошлой смены (продолжай логически):\n"
                f"Саша: {last_user}\n"
                f"Ассистент: {last_asst}"
            )
    return "\n\n".join(parts)


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
    turns: list[SimTurn] | None = None,
    *,
    profile_id: str,
    streaming: bool,
    video: bool = False,
    until_done: bool = False,
    skip_validation: bool = False,
    skip_profile_updates: bool = False,
) -> tuple[list[tuple[SimTurn, TurnResult]], list[dict[str, str]]]:
    agent.active_profile_id = profile_id
    agent.profiles.load()
    turn_list = list(turns) if turns else []
    turn_total: int | None = len(turn_list) if turn_list and not until_done else None
    results: list[tuple[SimTurn, TurnResult]] = []

    if video:
        clear_screen()
        print(f"\n[demo] === {title} ===")
        if sim.prior_summary.strip():
            print("[summary] user_sim помнит прошлую смену:")
            print(sim.prior_summary.strip())
            print()
        print_profile_block(agent)
        print_state_block(agent)
        wait_and_clear(WAIT_NEXT_STEP)
    else:
        print(f"\n[demo] === {title} ===")
        if sim.prior_summary.strip():
            print("[summary] user_sim помнит прошлую смену:")
            print(sim.prior_summary.strip())
            print()
        print_profile_block(agent)
        print_state_block(agent)

    transcript: list[dict[str, str]] = []
    turn_index = 0
    while True:
        if until_done:
            state = agent.task_state.state
            if state is not None and state.stage == Stage.DONE:
                break
        elif turn_index >= len(turn_list):
            break

        turn_index += 1
        if until_done:
            turn = SimTurn(str(turn_index))
        else:
            turn = turn_list[turn_index - 1]

        if video:
            clear_screen()
            print_turn_header(title, turn_index, turn_total, agent)
        user_text = sim.generate(transcript, turn=turn)
        print_user_reply(user_text, streaming=streaming)
        result = print_agent_turn(
            agent,
            user_text,
            streaming=streaming,
            skip_validation=skip_validation,
            skip_profile_updates=skip_profile_updates,
        )
        results.append((turn, result))
        transcript.append({"role": "user", "content": user_text})
        transcript.append({"role": "assistant", "content": result.reply})
        if video and (until_done or turn_index < len(turn_list)):
            wait_and_clear(WAIT_NEXT_STEP)
    return results, transcript


def demo_checklist(
    agent: ShelterAgent,
    all_fsm_lines: list[str],
) -> None:
    print("\n[demo] === чеклист переходов ===")
    ts = agent.task_state.state
    denied = any(line.startswith("denied ") for line in all_fsm_lines)
    allowed = any(line.startswith("allowed ") for line in all_fsm_lines)
    ok_case = ts is not None and ts.opossum == "Тофик"
    paused_ok = ts is not None and not ts.paused

    print(f"  {'✓' if denied else '✗'} был [transition] denied (skip)")
    print(f"  {'✓' if allowed else '✗'} был [transition] allowed (≥1)")
    print(f"  {'✓' if ok_case else '✗'} кейс Тофик / шар + погоня")
    if ts:
        done_ok = ts.stage == Stage.DONE
        print(f"  {'✓' if done_ok else '✗'} stage=done (финал demo)")
        if not done_ok:
            print(f"    (сейчас stage={ts.stage.value})")
        print(f"  {'✓' if paused_ok else '✗'} не на паузе (финал)")
    else:
        print("  ✗ FSM state missing")
    print(f"  short: {len(agent.memory.short.messages)} сообщений (текущая сессия)")


def cmd_show_memory() -> None:
    memory = MemoryStore(DATA_DIR)
    memory.load()
    profiles = ProfileStore(DATA_DIR)
    profiles.load()
    task_state = TaskStateStore(DATA_DIR / "working" / TIKTOK_CASE_FILE)
    task_state.load()
    invariants = InvariantStore(DATA_DIR / "long" / "invariants.json")
    invariants.load()
    reg_path = DATA_DIR / "long" / "tiktok_regulation.md"
    reg = reg_path.read_text(encoding="utf-8") if reg_path.exists() else ""
    print(memory.dump_layers())
    print()
    print("=== tiktok_regulation.md (фрагмент) ===")
    for line in reg.strip().splitlines()[:8]:
        print(f"  {line}")
    print()
    print(invariants.dump_section())
    print()
    print(task_state.dump_section())
    print()
    print(profiles.dump_section())


def cmd_clear(target: str) -> None:
    memory = MemoryStore(DATA_DIR)
    memory.load()
    profiles = ProfileStore(DATA_DIR)
    profiles.load()
    task_state = TaskStateStore(DATA_DIR / "working" / TIKTOK_CASE_FILE)
    task_state.load()
    invariants = InvariantStore(DATA_DIR / "long" / "invariants.json")
    invariants.load()
    if target in ("short", "all"):
        memory.clear_short()
        print("[memory] short cleared")
    if target in ("working", "all"):
        memory.clear_working()
        task_state.clear()
        print("[memory] working cleared (+ TikTok FSM)")
    if target in ("profiles", "all"):
        profiles.reset_to_seed()
        print("[profile] profiles reset to seed")
    if target == "all-long-reset":
        memory.reset_long()
        invariants.reset_to_seed()
        print("[memory] long reset (charter + invariants)")
    if target == "all":
        memory.reset_long()
        invariants.reset_to_seed()
        print("[memory] long reset (charter + invariants)")


def cmd_chat(agent: ShelterAgent, *, streaming: bool) -> None:
    print("Интерактивный чат (пустая строка или /quit — выход).")
    print("Профиль: sasha. Смена: /profile martha|klyk|director|sasha\n")
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
        print_agent_turn(agent, user_text, streaming=streaming)
        print_state_block(agent)
        print_tokens(agent)
        print()


def cmd_demo(config, *, streaming: bool, video: bool = False) -> None:
    agent = create_agent(DATA_DIR, config)
    agent.include_invariants = False
    agent.memory.clear_working()
    agent.memory.reset_long()
    agent.memory.clear_short()
    agent.profiles.reset_to_seed()
    agent.task_state.clear()
    agent.invariants.load()
    agent.memory.load()
    agent.profiles.load()
    agent.task_state.init_case("Тофик", "ролик: шар + погоня хозяина")

    sim = UserSimulator(config, persona="sasha", tracker=agent.tracker)
    sim.scenario = "sasha_tiktok"

    print_demo_intro(agent)
    if video:
        wait_and_clear(WAIT_DEMO_START)

    all_fsm_lines: list[str] = []

    turn_results, transcript_s1 = run_dialog(
        agent,
        sim,
        "сессия 1/2 — Саша, импровизация",
        sasha_demo_session1_turns(),
        profile_id="sasha",
        streaming=streaming,
        video=video,
        skip_validation=True,
        skip_profile_updates=True,
    )
    for _, result in turn_results:
        all_fsm_lines.extend(result.classifier.fsm_applied)

    resume_context = build_user_sim_resume(
        agent,
        transcript_s1,
        "сессия 1/2 — Саша, импровизация",
    )
    agent.memory.clear_short()
    agent.memory.load()
    agent.profiles.load()
    agent.task_state.load()

    if video:
        wait_and_clear(WAIT_NEXT_SESSION)
    else:
        print("\n[demo] --- пауза: short очищен, FSM сохранён ---")
        print_state_block(agent)
        if resume_context:
            print("[summary] для user_sim после паузы:")
            print(resume_context)
            print()

    sim.prior_summary = resume_context
    turn_results2, _ = run_dialog(
        agent,
        sim,
        "сессия 2/2 — после паузы, до done",
        until_done=True,
        profile_id="sasha",
        streaming=streaming,
        video=video,
        skip_validation=True,
        skip_profile_updates=True,
    )
    for _, result in turn_results2:
        all_fsm_lines.extend(result.classifier.fsm_applied)

    if video:
        wait_any_key("\n[demo] ── demo завершён. Любая клавиша → чеклист ──")
        clear_screen()

    if not video:
        print("\n[memory] dump:")
        print(agent.task_state.dump_section())

    demo_checklist(agent, all_fsm_lines)
    print_tokens(agent)
    if video:
        wait_any_key("\n[demo] ── конец. Любая клавиша ──")


def main() -> None:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="Приют «Хvostik» — TikTok FSM")
    parser.add_argument("--demo", action="store_true", help="demo Саша + TikTok Clips")
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
    if agent.task_state.state is None:
        agent.task_state.init_case("Тофик", "ролик: шар + погоня хозяина")
    cmd_chat(agent, streaming=streaming)


if __name__ == "__main__":
    main()
