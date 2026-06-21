"""CLI ассистента приюта «Хvостik» — day 04: инварианты + LLM-валидатор."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from agent import ShelterAgent, TurnResult, create_agent
from console_out import (
    WAIT_DEMO_START,
    WAIT_NEXT_STEP,
    StreamPrinter,
    clear_screen,
    typewriter_print,
    wait_and_clear,
    wait_any_key,
)
from invariant_validator import ValidationResult
from invariants import InvariantStore
from llm import load_llm_config
from memory import MemoryStore
from profiles import ProfileStore
from task_state import TaskStateStore
from user_sim import SimTurn, UserSimulator, martha_dumpster_turns

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
        "Операционный ассистент ночного приюта «Хvостik»: инварианты в отдельном store, "
        "LLM-валидатор проверяет каждый ответ."
    )
    print()
    print("Слои состояния (data/):")
    print("  short            — текущий диалог")
    print("  working          — карточки + adoption_case.json (FSM)")
    print("  long/charter.md  — устав")
    print("  long/invariants.json — инварианты (отдельно от диалога)")
    print("  profiles         — персонализация")
    print()
    print("Demo: **Марта после помойки** — 9 ходов давления на инварианты + recover.")
    print("  user_sim adversarial: цель — заставить агента нарушить правило.")
    print("  Провал черновика → [agent:invalid] + retry.")
    print()
    print(f"  long: смена {hours}")
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


def _validation_passed(expected: str, validation: ValidationResult | None) -> bool:
    if not expected or validation is None:
        return True
    if expected in validation.refused:
        return True
    return validation.pass_ and expected in validation.at_risk


def print_invariant_block(result: TurnResult) -> None:
    if result.validation_skipped:
        return
    dv = result.draft_validation
    fv = result.final_validation
    if dv is None:
        return

    if dv.at_risk:
        print(f"[invariant] at_risk: {', '.join(dv.at_risk)}")

    if result.retried:
        print("[invariant] ✗ draft REJECTED (не прошёл проверку)")
        for v in dv.violations:
            reason = v.get("reason", "")
            suffix = f" — {reason}" if reason else ""
            print(f"[invariant]   violation: {v.get('id', '?')}{suffix}")
        print(f"[agent:invalid] {result.draft_reply}\n")
        if fv and fv.pass_:
            print("[invariant] retry → pass")
        else:
            print("[invariant] ✗ retry STILL FAILING")
            if fv:
                for v in fv.violations:
                    reason = v.get("reason", "")
                    suffix = f" — {reason}" if reason else ""
                    print(f"[invariant]   violation: {v.get('id', '?')}{suffix}")
            if fv and not fv.pass_:
                print(f"[agent:invalid] {result.final_reply}\n")
                print("[invariant] ⚠ агент так и не прошёл проверку — см. checklist")
        if fv and fv.refused:
            print(f"[invariant] refused: {', '.join(fv.refused)}")
    elif dv.pass_:
        print("[invariant] pass")
        if dv.refused:
            print(f"[invariant] refused: {', '.join(dv.refused)}")
    else:
        print("[invariant] ✗ draft REJECTED (не прошёл проверку)")
        for v in dv.violations:
            reason = v.get("reason", "")
            suffix = f" — {reason}" if reason else ""
            print(f"[invariant]   violation: {v.get('id', '?')}{suffix}")


def print_agent_turn(
    agent: ShelterAgent,
    user_text: str,
    *,
    streaming: bool,
    skip_validation: bool = False,
) -> TurnResult:
    if streaming:
        printer = StreamPrinter("[agent] ")
        result = agent.run_turn(
            user_text,
            stream=True,
            on_delta=printer.on_delta,
            skip_validation=skip_validation,
        )
        printer.finish()
        if result.retried and result.final_reply != result.draft_reply:
            print_invariant_block(result)
            typewriter_print("[agent] ", result.final_reply)
        else:
            print_invariant_block(result)
    else:
        result = agent.run_turn(
            user_text, stream=False, skip_validation=skip_validation
        )
        if result.retried:
            print(f"[agent] {result.draft_reply}\n")
            print_invariant_block(result)
            print(f"[agent] {result.final_reply}\n")
        else:
            print(f"[agent] {result.final_reply}\n")
            print_invariant_block(result)
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


def seed_trial_period_case(agent: ShelterAgent) -> None:
    ts = agent.task_state
    ts.init_case("Оскар", "семья Ивановых")
    ts.add_artifact(
        "adoption_application",
        "Анкета семьи Ивановых",
        "Условия содержания соответствуют уставу.",
        "approved",
        "martha",
    )
    ts.advance()
    ts.add_artifact(
        "home_visit_act",
        "Акт домашнего визита",
        "Адрес и условия в норме.",
        "approved",
        "martha",
    )
    ts.advance()


def run_dialog(
    agent: ShelterAgent,
    sim: UserSimulator,
    title: str,
    turns: list[SimTurn],
    *,
    profile_id: str,
    streaming: bool,
    video: bool = False,
) -> list[tuple[SimTurn, TurnResult]]:
    agent.active_profile_id = profile_id
    agent.profiles.load()
    turn_list = list(turns)
    turn_total = len(turn_list)
    results: list[tuple[SimTurn, TurnResult]] = []

    if video:
        clear_screen()
        print(f"\n[demo] === {title} ===")
        print_profile_block(agent)
        print_state_block(agent)
        wait_and_clear(WAIT_NEXT_STEP)
    else:
        print(f"\n[demo] === {title} ===")
        print_profile_block(agent)
        print_state_block(agent)

    transcript: list[dict[str, str]] = []
    for turn_index, turn in enumerate(turn_list, start=1):
        if video:
            clear_screen()
            print_turn_header(title, turn_index, turn_total, agent)
        user_text = sim.generate(transcript, turn=turn)
        print_user_reply(user_text, streaming=streaming)
        result = print_agent_turn(
            agent,
            user_text,
            streaming=streaming,
            skip_validation=turn.skip_validation,
        )
        print_classifier_events(result.classifier)
        results.append((turn, result))
        transcript.append({"role": "user", "content": user_text})
        transcript.append({"role": "assistant", "content": result.reply})
        if video and turn_index < turn_total:
            wait_and_clear(WAIT_NEXT_STEP)
    return results


def demo_checklist(
    agent: ShelterAgent,
    turn_results: list[tuple[SimTurn, TurnResult]],
) -> None:
    print("\n[demo] === чеклист инвариантов ===")
    all_final_ok = True
    any_draft_breached = False

    for turn, result in turn_results:
        if not turn.expected_invariant:
            continue
        exp = turn.expected_invariant
        fv = result.final_validation
        dv = result.draft_validation

        final_ok = _validation_passed(exp, fv)
        all_final_ok = all_final_ok and final_ok
        draft_breached = (
            dv is not None and not dv.pass_ and not result.validation_skipped
        )
        if draft_breached:
            any_draft_breached = True

        mark_a = "✓" if final_ok else "✗"
        if draft_breached:
            draft_line = "    ✓ draft REJECTED — sim пробил черновик"
        else:
            draft_line = "    — v1 сразу pass (sim не пробил)"
        print(f"  {mark_a} финал {exp}")
        print(draft_line)

    print()
    print(f"  {'✓' if all_final_ok else '✗'} инварианты выстояли (все 9 финалов)")
    print(
        f"  {'✓' if any_draft_breached else '✗'} adversarial sim: был хотя бы один REJECTED draft"
    )
    print(f"  {agent.invariants.stats_line()}")
    print(f"  short: {len(agent.memory.short.messages)} сообщений")


def cmd_show_memory() -> None:
    memory = MemoryStore(DATA_DIR)
    memory.load()
    profiles = ProfileStore(DATA_DIR)
    profiles.load()
    task_state = TaskStateStore(DATA_DIR / "working" / "adoption_case.json")
    task_state.load()
    invariants = InvariantStore(DATA_DIR / "long" / "invariants.json")
    invariants.load()
    print(memory.dump_layers())
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
    task_state = TaskStateStore(DATA_DIR / "working" / "adoption_case.json")
    task_state.load()
    invariants = InvariantStore(DATA_DIR / "long" / "invariants.json")
    invariants.load()
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
        invariants.reset_to_seed()
        print("[memory] long reset (charter + invariants)")
    if target == "all":
        memory.reset_long()
        invariants.reset_to_seed()
        print("[memory] long reset (charter + invariants)")


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
    agent.invariants.load()
    agent.memory.load()
    agent.profiles.load()
    seed_trial_period_case(agent)

    sim = UserSimulator(
        config,
        persona="martha_dumpster",
        tracker=agent.tracker,
    )
    sim.scenario = "martha_dumpster"

    print_demo_intro(agent)
    if video:
        wait_and_clear(WAIT_DEMO_START)

    turn_results = run_dialog(
        agent,
        sim,
        "Марта + помойка — инварианты",
        martha_dumpster_turns(),
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
        print(agent.invariants.dump_section())
        print()
        print(agent.task_state.dump_section())
    demo_checklist(agent, turn_results)
    print_tokens(agent)
    if video:
        wait_any_key("\n[demo] ── конец. Любая клавиша ──")


def main() -> None:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="Приют «Хvостik» — инварианты")
    parser.add_argument("--demo", action="store_true", help="demo Марта + помойка")
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
