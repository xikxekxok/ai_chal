"""CLI для чат-агента с персистентной историей: one-shot или интерактивный режим."""

from __future__ import annotations

import argparse
import sys

from agent import DEFAULT_HISTORY_PATH, ChatAgent, load_agent_config

DEFAULT_PROMPT = "Объясни, что такое AI-агент, в двух предложениях."


def preview(text: str, limit: int = 120) -> str:
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
    print(f"[agent] ответ ({len(reply)} символов): {preview(reply)}")
    usage = agent.last_usage
    if usage:
        print(
            f"[usage] prompt={usage.get('prompt_tokens', '?')} "
            f"completion={usage.get('completion_tokens', '?')}"
        )
    print(f"[store] сохранено {agent.message_count} сообщений")


def run_once(agent: ChatAgent, prompt: str) -> None:
    print(f"[agent] model: {agent.model}")
    print(f"[user] {preview(prompt)}")
    reply = agent.run(prompt)
    print_agent_reply(agent, reply)


def run_chat(agent: ChatAgent) -> None:
    print(f"[agent] model: {agent.model}")
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
        print(f"[store] сохранено {agent.message_count} сообщений")


def parse_args(argv: list[str]) -> tuple[argparse.Namespace, str]:
    parser = argparse.ArgumentParser(
        description="LLM-агент с сохранением истории диалога в JSON."
    )
    parser.add_argument(
        "--chat",
        action="store_true",
        help="Интерактивный режим (история сохраняется между запусками).",
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
    print_store_status(agent)

    if args.chat:
        run_chat(agent)
        return

    run_once(agent, prompt)


if __name__ == "__main__":
    main()
