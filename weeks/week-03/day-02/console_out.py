"""Потоковая печать реплик в stdout (demo/chat)."""

from __future__ import annotations

import sys
import time

USER_REPLICA_DURATION_SEC = 2.0
TYPEWRITER_CHUNK = 8


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
        text[offset : offset + TYPEWRITER_CHUNK]
        for offset in range(0, len(text), TYPEWRITER_CHUNK)
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
