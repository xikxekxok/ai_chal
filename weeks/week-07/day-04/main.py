"""Week 07 day 04: local file assistant."""

from __future__ import annotations

import argparse
import sys

from agent import FileAssistant
from llm import load_llm_config
from paths import WORKSPACE_ROOT
from tools import ToolExecutor, ensure_workspace, reset_workspace

DEMO_PROMPTS = [
    (
        "Find every usage of fetch_user across this sandbox project. "
        "List files with line numbers and briefly explain each usage."
    ),
    (
        "Update README.md in this sandbox workspace. Base it only on the actual code. "
        "Mention the project purpose, files, and where fetch_user is used."
    ),
]


def print_tokens(assistant: FileAssistant) -> None:
    tracker = assistant.tracker
    print(
        f"[tokens] calls={tracker.calls} "
        f"prompt={tracker.prompt_tokens} completion={tracker.completion_tokens}"
    )


def run_tools_test() -> int:
    workspace = reset_workspace()
    executor = ToolExecutor(workspace)
    search_result = executor.call("search_files", {"query": "fetch_user"})
    print(f"[demo] tools smoke inside {workspace}")
    print(f"[tool] list_dir(.) -> {executor.call('list_dir', {'path': '.'})}")
    print(f"[tool] search_files(fetch_user) -> {search_result}")
    before = executor.call("read_file", {"path": "README.md"})
    print(f"[tool] read_file(README.md) -> {before}")
    updated = (
        "# Sandbox Service\n\n"
        "Temporary README for tools smoke test.\n"
        "- api.py defines fetch_user().\n"
        "- app.py and handlers.py use it.\n"
    )
    print(
        f"[tool] write_file(README.md) -> "
        f"{executor.call('write_file', {'path': 'README.md', 'content': updated})}"
    )
    return 0


def run_prompt(prompt: str) -> int:
    ensure_workspace()
    config = load_llm_config()
    assistant = FileAssistant(config=config)
    print(f"[agent] prompt: {prompt}")
    result = assistant.run(prompt)
    print(f"[agent] {result.reply}")
    print_tokens(assistant)
    return 0


def run_demo() -> int:
    print("[demo] Week 07 Day 04 - AI file assistant with local tools")
    print(f"[demo] workspace: {WORKSPACE_ROOT}")
    for index, prompt in enumerate(DEMO_PROMPTS, start=1):
        reset_workspace()
        print()
        print(f"[demo] scenario {index}")
        exit_code = run_prompt(prompt)
        if exit_code != 0:
            return exit_code
    return 0


def run_chat() -> int:
    ensure_workspace()
    config = load_llm_config()
    assistant = FileAssistant(config=config)
    print("[demo] interactive chat, commands: /reset, /quit")
    while True:
        try:
            prompt = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not prompt:
            continue
        if prompt in {"/quit", "/exit"}:
            return 0
        if prompt == "/reset":
            reset_workspace()
            assistant = FileAssistant(config=config)
            print("[demo] workspace reset")
            continue
        result = assistant.run(prompt)
        print(f"[agent] {result.reply}")
        print_tokens(assistant)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI file assistant with local tools.")
    parser.add_argument("prompt", nargs="?", help="One-shot goal for the assistant.")
    parser.add_argument(
        "--tools-test",
        action="store_true",
        help="Run tool smoke test without LLM.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset sandbox workspace before other actions.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run two prepared demo scenarios.",
    )
    parser.add_argument("--chat", action="store_true", help="Interactive assistant chat.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.reset:
        workspace = reset_workspace()
        print(f"[demo] workspace reset: {workspace}")
        if not (args.tools_test or args.demo or args.chat or args.prompt):
            return 0

    if args.tools_test:
        return run_tools_test()
    if args.demo:
        return run_demo()
    if args.chat:
        return run_chat()
    if args.prompt:
        return run_prompt(args.prompt)

    print("[error] Provide a prompt or one of: --tools-test, --demo, --chat", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
