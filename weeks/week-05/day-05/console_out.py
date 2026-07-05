"""ANSI-цвета для stdout."""

from __future__ import annotations

import os
import sys

RESET = "\033[0m"

TAG_STYLE: dict[str, str] = {
    "user": "1;96",
    "agent": "1;92",
    "store": "90",
    "scenario": "36",
    "index": "90",
    "translate": "96",
    "query": "96",
    "retrieve": "33",
    "rerank": "35",
    "rag": "1;92",
    "sources": "1;94",
    "citations": "1;96",
    "retry": "91",
    "error": "91",
    "log": "90",
}

BODY_STYLE: dict[str, str] = {
    "user": "97",
    "agent": "92",
    "sources": "94",
    "citations": "96",
    "index": "37",
}


def use_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def style(text: str, sgr: str) -> str:
    if not use_color():
        return text
    return f"\033[{sgr}m{text}{RESET}"


def tag_label(tag: str) -> str:
    return style(f"[{tag}]", TAG_STYLE.get(tag, "37"))


def tag_visible_prefix(tag: str) -> str:
    return f"[{tag}] "


def body_indent(tag: str) -> str:
    return " " * len(tag_visible_prefix(tag))


def print_section(tag: str, body: str, *, layout: str = "hang") -> None:
    body_sgr = BODY_STYLE.get(tag, "37")
    lines = body.splitlines() if body else [""]
    if layout == "block":
        print(tag_label(tag), flush=True)
        for line in lines:
            styled = style(line, body_sgr) if use_color() else line
            print(styled, flush=True)
        print(flush=True)
        return
    prefix = f"{tag_label(tag)} "
    first = style(lines[0], body_sgr) if use_color() else lines[0]
    print(f"{prefix}{first}", flush=True)
    indent = body_indent(tag)
    for line in lines[1:]:
        styled = style(line, body_sgr) if use_color() else line
        print(f"{indent}{styled}", flush=True)
    print(flush=True)


def print_index_line(text: str) -> None:
    if text.startswith("[index]"):
        rest = text.removeprefix("[index]").lstrip()
        print(f"{tag_label('index')} {rest}", flush=True)
    else:
        print(f"{tag_label('index')} {text}", flush=True)


def print_tagged(tag: str, text: str) -> None:
    print(f"{tag_label(tag)} {text}", flush=True)


def pause(prompt: str, *, no_pause: bool) -> None:
    if no_pause:
        return
    styled = style(prompt, "90") if use_color() else prompt
    try:
        input(styled)
    except EOFError:
        print()
