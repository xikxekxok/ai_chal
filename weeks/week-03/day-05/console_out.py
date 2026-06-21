"""Потоковая печать реплик в stdout (demo/chat)."""

from __future__ import annotations

import sys
import termios
import time
import tty

USER_REPLICA_DURATION_SEC = 2.0
TYPEWRITER_CHUNK = 8

WAIT_NEXT_STEP = "\n[demo] ── ожидаем переход к следующему шагу — любая клавиша ──"
WAIT_NEXT_SESSION = "\n[demo] ── конец сессии. Любая клавиша → следующая сессия ──"
WAIT_DEMO_START = "\n[demo] ── готовы? Любая клавиша → начало demo ──"


def clear_screen() -> None:
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def wait_any_key(prompt: str = WAIT_NEXT_STEP) -> None:
    """Ждать нажатия любой клавиши (TTY). Иначе — Enter."""
    print(prompt, flush=True)
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


class StreamPrinter:
    """Печатает prefix один раз, затем чанки по мере прихода."""

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
    prefix: str,
    text: str,
    *,
    duration_sec: float = USER_REPLICA_DURATION_SEC,
) -> None:
    """Показать готовую реплику user_sim за ~duration_sec (адаптивно по длине)."""
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
        sys.stdout.write(chunk)
        sys.stdout.flush()
        if index + 1 < len(chunks):
            target_elapsed = duration_sec * (index + 1) / len(chunks)
            sleep_for = target_elapsed - (time.perf_counter() - start)
            if sleep_for > 0:
                time.sleep(sleep_for)
    print("\n", flush=True)
