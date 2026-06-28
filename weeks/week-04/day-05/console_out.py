"""Потоковая печать, ANSI-цвета и асинхронный постраничный вывод."""

from __future__ import annotations

import enum
import os
import queue
import select
import shutil
import sys
import termios
import threading
import time
import tty
from dataclasses import dataclass, field
from typing import Any

USER_REPLICA_DURATION_SEC = 2.0
TYPEWRITER_CHUNK = 8

RESET = "\033[0m"

TAG_STYLE: dict[str, str] = {
    "holmes": "1;96",
    "watson": "1;92",
    "mcp": "33",
    "report": "1;35",
    "witness": "1;34",
    "dossier": "1;94",
    "archive": "94",
    "clue": "1;93",
    "trail": "1;32",
    "deduction": "1;95",
    "verdict": "1;91",
    "error": "91",
    "demo": "36",
    "tokens": "90",
    "mcp-test": "90",
}

BODY_STYLE: dict[str, str] = {
    "holmes": "96",
    "watson": "92",
    "report": "37",
    "witness": "37",
    "dossier": "97",
    "archive": "37",
    "clue": "93",
    "trail": "92",
    "deduction": "95",
    "verdict": "91",
}

WAIT_NEXT_STEP = "\n[demo] ── ожидаем переход к следующему шагу — любая клавиша ──"
WAIT_DEMO_START = "\n[demo] ── готовы? Любая клавиша → начало demo ──"
PAGER_PROMPT = "[pager] Space/Enter — следующая страница · q — выход"

_pager_enabled = False


def use_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def pager_enabled() -> bool:
    return _pager_enabled


def enable_pager(*, clear: bool = True, lines: int | None = None) -> None:
    global _pager_enabled, _display
    _pager_enabled = True
    _display = PagerDisplay(clear=clear, page_height=lines)
    _display.start()


def reset_pager_display() -> None:
    if _display is not None:
        _display.reset_page()


def drain_display() -> None:
    if _display is not None:
        _display.drain()


def shutdown_display() -> None:
    global _display
    if _display is not None:
        _display.stop()
        _display = None


def pager_section() -> None:
    """Совместимость: разрыв только по высоте страницы, не по блокам."""
    return


def style(text: str, sgr: str) -> str:
    if not use_color():
        return text
    return f"\033[{sgr}m{text}{RESET}"


def tag_label(tag: str) -> str:
    return style(f"[{tag}]", TAG_STYLE.get(tag, "37"))


def tag_close(tag: str) -> str:
    label = f"[/{tag}]"
    return style(label, "90") if use_color() else label


def _terminal_rows_count() -> int:
    try:
        return shutil.get_terminal_size().lines
    except OSError:
        return 24


def _terminal_page_height() -> int:
    return _terminal_rows_count()


def clear_screen() -> None:
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def _read_key() -> str:
    if not sys.stdin.isatty():
        try:
            input()
        except EOFError:
            pass
        return " "
    fd = sys.stdin.fileno()
    try:
        old = termios.tcgetattr(fd)
    except termios.error:
        try:
            input()
        except EOFError:
            pass
        return " "
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b" and select.select([sys.stdin], [], [], 0.02)[0]:
            sys.stdin.read(2)
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


class UnitKind(enum.Enum):
    TAGGED = "tagged"
    BLOCK = "block"
    MCP = "mcp"
    REPLY = "reply"
    LINE = "line"


@dataclass
class DisplayUnit:
    kind: UnitKind
    payload: dict[str, Any] = field(default_factory=dict)
    cached: bool = False


def tag_visible_prefix(tag: str) -> str:
    return f"[{tag}] "


def reply_indent(tag: str) -> str:
    return " " * len(tag_visible_prefix(tag))


class PagerDisplay:
    _STOP = object()

    def __init__(self, *, clear: bool = True, page_height: int | None = None) -> None:
        self._clear = clear
        self._terminal_rows = page_height or _terminal_rows_count()
        self._content_height = max(self._terminal_rows - 1, 6)
        self._page_lines = 0
        self._badge_on_page = False
        self._q: queue.Queue[Any] = queue.Queue()
        self._thread: threading.Thread | None = None

    def reset_page(self) -> None:
        self._page_lines = 0
        self._badge_on_page = False

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="pager-display", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._q.put(self._STOP)
        if self._thread is not None:
            self._thread.join()

    def drain(self) -> None:
        self._q.join()

    def submit(self, unit: DisplayUnit) -> None:
        unit.cached = self._q.qsize() > 0
        self._q.put(unit)

    def _run(self) -> None:
        while True:
            item = self._q.get()
            try:
                if item is self._STOP:
                    break
                self._render(item)
            finally:
                self._q.task_done()

    def _terminal_cols(self) -> int:
        try:
            return shutil.get_terminal_size().columns
        except OSError:
            return 80

    def _print_badge(self, mode: str) -> None:
        label = " LIVE " if mode == "live" else " CACHED "
        sgr = "1;96" if mode == "live" else "1;33"
        styled = style(label, sgr)
        col = max(self._terminal_cols() - len(label), 1)
        sys.stdout.write(f"\033[1;{col}H{styled}")
        sys.stdout.write("\033[2;1H")
        sys.stdout.flush()

    def _open_page(self, mode: str) -> None:
        """Строка 1 — бейдж, строки 2..N — контент."""
        self._page_lines = 0
        self._print_badge(mode)
        self._badge_on_page = True

    def _pager_wait(self, mode: str) -> None:
        prompt = style(PAGER_PROMPT, "90") if use_color() else PAGER_PROMPT
        print(prompt, flush=True)
        key = _read_key()
        if key in {"q", "Q", "\x03"}:
            print(f"{tag_label('demo')} остановлено.", flush=True)
            raise SystemExit(0)
        if self._clear:
            clear_screen()
        self._badge_on_page = False
        self._open_page(mode)

    def _ensure_page(self, mode: str) -> None:
        if not self._badge_on_page:
            self._open_page(mode)

    def _put_content_line(self, line: str, mode: str) -> None:
        if self._page_lines >= self._content_height:
            self._pager_wait(mode)
        self._ensure_page(mode)
        print(line, flush=True)
        self._page_lines += 1
        if self._page_lines < self._content_height:
            row = 2 + self._page_lines
            sys.stdout.write(f"\033[{row};1H")
            sys.stdout.flush()

    def _render_step_lines(
        self,
        lines: list[str],
        cached: bool,
        *,
        typewriter: bool = False,
    ) -> None:
        mode = "cached" if cached else "live"
        if not lines:
            return

        idx = 0
        while idx < len(lines):
            remaining = self._content_height - self._page_lines
            left = len(lines) - idx

            if left <= remaining:
                for k in range(idx, len(lines)):
                    if typewriter and cached:
                        self._typewriter_single_line(lines[k], mode)
                    else:
                        self._put_content_line(lines[k], mode)
                return

            if len(lines) > self._content_height:
                chunk = remaining if remaining > 0 else self._content_height
                if chunk <= 0:
                    self._pager_wait(mode)
                    continue
                chunk = min(chunk, self._content_height - self._page_lines)
                if chunk <= 0:
                    self._pager_wait(mode)
                    continue
                for k in range(idx, idx + chunk):
                    self._put_content_line(lines[k], mode)
                idx += chunk
                if idx < len(lines):
                    self._pager_wait(mode)
                continue

            self._pager_wait(mode)
            idx = 0

    def _typewriter_single_line(self, line: str, mode: str) -> None:
        if self._page_lines >= self._content_height:
            self._pager_wait(mode)
        self._ensure_page(mode)
        if not line:
            print(flush=True)
            self._page_lines += 1
            return
        start = time.perf_counter()
        chunks = [
            line[offset : offset + TYPEWRITER_CHUNK]
            for offset in range(0, len(line), TYPEWRITER_CHUNK)
        ]
        for index, chunk in enumerate(chunks):
            sys.stdout.write(chunk)
            sys.stdout.flush()
            if index + 1 < len(chunks):
                target = USER_REPLICA_DURATION_SEC * (index + 1) / len(chunks)
                sleep_for = target - (time.perf_counter() - start)
                if sleep_for > 0:
                    time.sleep(sleep_for)
        print(flush=True)
        self._page_lines += 1
        if self._page_lines < self._content_height:
            row = 2 + self._page_lines
            sys.stdout.write(f"\033[{row};1H")
            sys.stdout.flush()

    def _typewriter_tagged(self, tag: str, text: str, mode: str) -> None:
        prefix = f"{tag_label(tag)} "
        body_sgr = BODY_STYLE.get(tag, "37")
        full = f"{prefix}{style(text, body_sgr) if use_color() else text}"
        self._render_step_lines([full], cached=True, typewriter=True)

    def _unit_lines(self, unit: DisplayUnit) -> list[str]:
        if unit.kind == UnitKind.LINE:
            return [unit.payload["line"]]
        if unit.kind == UnitKind.TAGGED:
            tag = unit.payload["tag"]
            text = unit.payload["text"]
            return [f"{tag_label(tag)} {text}"]
        if unit.kind == UnitKind.MCP:
            server = unit.payload["server"]
            call_label = unit.payload["call_label"]
            if use_color():
                line = (
                    f"{tag_label('mcp')} {style(server, '1;96')} {style('→', '90')} "
                    f"{style(call_label, '37')}"
                )
            else:
                line = f"[mcp] {server} → {call_label}"
            return [line]
        if unit.kind == UnitKind.BLOCK:
            tag = unit.payload["tag"]
            title = unit.payload["title"]
            body = unit.payload["body"]
            title_style = TAG_STYLE.get(tag, "1;37")
            sep = style("──", "90")
            header = f"{tag_label(tag)} {sep} {style(title, title_style)} {sep}"
            lines = [header]
            body_sgr = BODY_STYLE.get(tag, "37")
            for body_line in (body.rstrip().splitlines() if body else []):
                lines.append(style(body_line, body_sgr) if use_color() else body_line)
            lines.append(tag_close(tag))
            return lines
        if unit.kind == UnitKind.REPLY:
            tag = unit.payload["tag"]
            text = unit.payload["text"]
            prefix = f"{tag_label(tag)} "
            body_sgr = BODY_STYLE.get(tag, "97" if tag == "watson" else "37")
            indent = reply_indent(tag)
            if not text:
                return [prefix.rstrip()]
            parts = text.splitlines()
            lines = [
                f"{prefix}{style(parts[0], body_sgr) if use_color() else parts[0]}",
            ]
            for part in parts[1:]:
                body = style(part, body_sgr) if use_color() else part
                lines.append(f"{indent}{body}")
            return lines
        return []

    def _render(self, unit: DisplayUnit) -> None:
        mode = "cached" if unit.cached else "live"
        if unit.cached and unit.kind == UnitKind.TAGGED:
            self._typewriter_tagged(unit.payload["tag"], unit.payload["text"], mode)
            return
        if unit.cached and unit.kind == UnitKind.REPLY:
            lines = self._unit_lines(unit)
            self._render_step_lines(lines, cached=True, typewriter=True)
            return
        lines = self._unit_lines(unit)
        self._render_step_lines(lines, unit.cached)


_display: PagerDisplay | None = None


def _submit(kind: UnitKind, **payload: Any) -> None:
    if _display is not None:
        _display.submit(DisplayUnit(kind=kind, payload=payload))
        return
    _direct_print(kind, **payload)


def _direct_print(kind: UnitKind, **payload: Any) -> None:
    if kind == UnitKind.TAGGED:
        print(f"{tag_label(payload['tag'])} {payload['text']}", flush=True)
    elif kind == UnitKind.LINE:
        print(payload["line"], flush=True)
    elif kind == UnitKind.BLOCK:
        print_block_direct(payload["tag"], payload["title"], payload["body"])
    elif kind == UnitKind.MCP:
        print_mcp_direct(payload["server"], payload["call_label"])
    elif kind == UnitKind.REPLY:
        print_reply_direct(payload["tag"], payload["text"], stream=payload.get("stream", False))


def print_block_direct(tag: str, title: str, body: str) -> None:
    title_style = TAG_STYLE.get(tag, "1;37")
    sep = style("──", "90")
    header = f"{tag_label(tag)} {sep} {style(title, title_style)} {sep}"
    print(header, flush=True)
    if body:
        body_sgr = BODY_STYLE.get(tag, "37")
        for line in body.rstrip().splitlines():
            print(style(line, body_sgr), flush=True)
    print(tag_close(tag), flush=True)


def print_mcp_direct(server: str, call_label: str) -> None:
    if use_color():
        line = (
            f"{tag_label('mcp')} {style(server, '1;96')} {style('→', '90')} "
            f"{style(call_label, '37')}"
        )
    else:
        line = f"[mcp] {server} → {call_label}"
    print(line, flush=True)


def print_reply_direct(tag: str, text: str, *, stream: bool) -> None:
    if stream:
        typewriter_print_direct(tag, text)
    else:
        prefix = f"{tag_label(tag)} "
        body_style = BODY_STYLE.get(tag, "97" if tag == "watson" else "37")
        indent = reply_indent(tag)
        if not text:
            print(prefix.rstrip(), flush=True)
            return
        lines = text.splitlines()
        first = style(lines[0], body_style) if use_color() else lines[0]
        print(f"{prefix}{first}", flush=True)
        for line in lines[1:]:
            body = style(line, body_style) if use_color() else line
            print(f"{indent}{body}", flush=True)


def typewriter_print_direct(
    tag: str,
    text: str,
    *,
    duration_sec: float = USER_REPLICA_DURATION_SEC,
) -> None:
    prefix = f"{tag_label(tag)} "
    body_style = BODY_STYLE.get(tag, "97" if tag == "watson" else "37")
    sys.stdout.write(prefix)
    sys.stdout.flush()
    if not text:
        print("\n", flush=True)
        return
    start = time.perf_counter()
    chunks = [
        text[offset : offset + TYPEWRITER_CHUNK] for offset in range(0, len(text), TYPEWRITER_CHUNK)
    ]
    for index, chunk in enumerate(chunks):
        styled = style(chunk, body_style) if use_color() else chunk
        sys.stdout.write(styled)
        sys.stdout.flush()
        if index + 1 < len(chunks):
            target_elapsed = duration_sec * (index + 1) / len(chunks)
            sleep_for = target_elapsed - (time.perf_counter() - start)
            if sleep_for > 0:
                time.sleep(sleep_for)
    print("\n", flush=True)


def print_tagged(tag: str, text: str) -> None:
    _submit(UnitKind.TAGGED, tag=tag, text=text)


def print_block(tag: str, title: str, body: str) -> None:
    _submit(UnitKind.BLOCK, tag=tag, title=title, body=body)


def print_mcp(server: str, call_label: str) -> None:
    _submit(UnitKind.MCP, server=server, call_label=call_label)


def print_demo_line(text: str) -> None:
    if text.startswith("[demo]"):
        rest = text.removeprefix("[demo]").lstrip()
        _submit(UnitKind.LINE, line=f"{tag_label('demo')} {rest}")
    else:
        print_tagged("demo", text)


def print_tokens_line(text: str) -> None:
    line = style(text, TAG_STYLE["tokens"]) if use_color() else text
    _submit(UnitKind.LINE, line=line)


def wait_any_key(prompt: str = WAIT_NEXT_STEP) -> None:
    print(style(prompt, "90") if use_color() else prompt, flush=True)
    if not sys.stdin.isatty():
        try:
            input()
        except EOFError:
            pass
        return
    fd = sys.stdin.fileno()
    try:
        old = termios.tcgetattr(fd)
    except termios.error:
        try:
            input()
        except EOFError:
            pass
        return
    try:
        tty.setraw(fd)
        sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    print(flush=True)


def wait_and_clear(prompt: str = WAIT_NEXT_STEP) -> None:
    wait_any_key(prompt)
    clear_screen()
    reset_pager_display()


class StreamPrinter:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self._started = False

    def on_delta(self, chunk: str) -> None:
        if not chunk:
            return
        if not self._started:
            sys.stdout.write(self.prefix)
            self._started = True
        sys.stdout.write(chunk)
        sys.stdout.flush()

    def finish(self) -> None:
        if self._started:
            print("\n", flush=True)
        else:
            print(f"{self.prefix}\n", flush=True)


def typewriter_print(
    tag: str,
    text: str,
    *,
    duration_sec: float = USER_REPLICA_DURATION_SEC,
) -> None:
    if _display is not None:
        _submit(UnitKind.REPLY, tag=tag, text=text, stream=True)
        return
    typewriter_print_direct(tag, text, duration_sec=duration_sec)


def print_reply(tag: str, text: str, *, stream: bool) -> None:
    if _display is not None:
        _submit(UnitKind.REPLY, tag=tag, text=text, stream=stream)
        return
    print_reply_direct(tag, text, stream=stream)
