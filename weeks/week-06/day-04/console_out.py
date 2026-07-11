"""ANSI-цвета для stdout."""

from __future__ import annotations

import os
import sys

RESET = "\033[0m"

TAG_STYLE: dict[str, str] = {
    "question": "1;96",
    "expect": "1;93",
    "question-en": "1;94",
    "demo": "36",
    "index": "90",
    "cloud": "96",
    "local": "1;92",
    "translate": "96",
    "retrieve": "33",
    "rerank": "35",
    "stage-cite": "1;93",
    "stage-simple": "1;36",
    "stage-rerank": "1;93",
    "stage-wide": "1;36",
    "fallback": "1;33",
    "context-rerank": "1;33",
    "context-wide": "1;33",
    "rag-rerank": "1;92",
    "rag-wide": "1;36",
    "sources-rerank": "1;94",
    "sources-wide": "1;94",
    "citations-rerank": "1;96",
    "citations-wide": "1;96",
    "chunks-rerank": "1;94",
    "chunks-wide": "1;94",
    "answer-rag": "1;92",
    "thinking": "90",
    "raw-response": "1;91",
    "retry": "91",
    "error": "91",
}

BODY_STYLE: dict[str, str] = {
    "question": "97",
    "expect": "93",
    "question-en": "94",
    "index": "37",
    "stage-cite": "93",
    "stage-simple": "36",
    "stage-rerank": "93",
    "stage-wide": "36",
    "fallback": "33",
    "context-rerank": "33",
    "context-wide": "33",
    "rag-rerank": "92",
    "rag-wide": "36",
    "sources-rerank": "94",
    "sources-wide": "94",
    "citations-rerank": "96",
    "citations-wide": "96",
    "chunks-rerank": "94",
    "chunks-wide": "94",
    "answer-rag": "92",
    "thinking": "90",
    "raw-response": "91",
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


def print_demo_line(text: str) -> None:
    if text.startswith("[demo]"):
        rest = text.removeprefix("[demo]").lstrip()
        print(f"{tag_label('demo')} {rest}", flush=True)
    else:
        print(f"{tag_label('demo')} {text}", flush=True)


def print_index_line(text: str) -> None:
    if text.startswith("[index]"):
        rest = text.removeprefix("[index]").lstrip()
        print(f"{tag_label('index')} {rest}", flush=True)
    else:
        print(f"{tag_label('index')} {text}", flush=True)


FALLBACK_BAR = "=" * 72


def print_fallback_banner(*, chunk_count: int) -> None:
    line = (
        f"fallback: ответ после rerank недостаточен → "
        f"повтор с {chunk_count} cosine-чанками без rerank"
    )
    print()
    print(FALLBACK_BAR)
    print_section("fallback", line)
    print(FALLBACK_BAR)
    print()


def print_stage_header(stage: str, title: str) -> None:
    tag = f"stage-{stage}"
    print_section(tag, title, layout="block")


def print_tagged(tag: str, text: str) -> None:
    print(f"{tag_label(tag)} {text}", flush=True)


def clear_screen() -> None:
    if sys.stdout.isatty():
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()
    else:
        print("\n" + "=" * 72 + "\n")


def pause(prompt: str, *, no_pause: bool) -> None:
    if no_pause:
        return
    styled = style(prompt, "90") if use_color() else prompt
    try:
        input(styled)
    except EOFError:
        print()


_active_stream_tag: str | None = None


def begin_stream_section(tag: str) -> None:
    global _active_stream_tag
    if _active_stream_tag == tag:
        return
    if _active_stream_tag is not None:
        end_stream_section()
    _active_stream_tag = tag
    print(f"{tag_label(tag)} ", end="", flush=True)


def write_stream_delta(text: str, *, tag: str) -> None:
    if not text:
        return
    body_sgr = BODY_STYLE.get(tag, "37")
    styled = style(text, body_sgr) if use_color() else text
    sys.stdout.write(styled)
    sys.stdout.flush()


def end_stream_section() -> None:
    global _active_stream_tag
    if _active_stream_tag is None:
        return
    _active_stream_tag = None
    print("\n", flush=True)
