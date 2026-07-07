"""CLI для локального чат-агента: one-shot или интерактивный режим."""

from __future__ import annotations

import argparse
import sys

from agent import ChatAgent, load_agent_config
from llm import check_ollama, load_ollama_config

DEFAULT_PROMPT = "Объясни, что такое AI-агент, в двух предложениях."


def preview(text: str, limit: int = 120) -> str:
    one_line = " ".join(text.split())
    if len(one_line) <= limit:
        return one_line
    return one_line[: limit - 1] + "…"


def print_agent_reply(agent: ChatAgent, reply: str) -> None:
    print(f"[local] ответ ({len(reply)} символов): {preview(reply)}")
    print(f"[latency] {agent.last_latency_ms} ms")
    usage = agent.last_usage
    if usage:
        print(
            f"[usage] prompt={usage.get('prompt_tokens', '?')} "
            f"completion={usage.get('completion_tokens', '?')}"
        )


def run_once(agent: ChatAgent, prompt: str) -> None:
    cfg = load_ollama_config()
    print(f"[local] model: {agent.model} (think={cfg.think})")
    print(f"[user] {preview(prompt)}")
    reply = agent.run(prompt)
    print_agent_reply(agent, reply)


def run_chat(agent: ChatAgent) -> None:
    cfg = load_ollama_config()
    print(f"[local] model: {agent.model} (think={cfg.think})")
    print("[local] интерактивный чат (quit / exit / q — выход)")
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
        print(f"[latency] {agent.last_latency_ms} ms")


def parse_args(argv: list[str]) -> tuple[argparse.Namespace, str]:
    parser = argparse.ArgumentParser(
        description="Локальный чат-агент через Ollama."
    )
    parser.add_argument(
        "--chat",
        action="store_true",
        help="Интерактивный режим (история накапливается между ходами).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Проверить Ollama и модель без генерации.",
    )
    args, rest = parser.parse_known_args(argv)
    prompt = " ".join(rest).strip() or DEFAULT_PROMPT
    return args, prompt


def main() -> None:
    args, prompt = parse_args(sys.argv[1:])

    if args.check:
        check_ollama()
        print("[done] check OK")
        return

    agent = ChatAgent(load_agent_config())

    if args.chat:
        run_chat(agent)
        return

    run_once(agent, prompt)


if __name__ == "__main__":
    main()
