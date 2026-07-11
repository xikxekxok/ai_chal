"""Rate limit и обрезка контекста."""

from __future__ import annotations

import time
from collections import defaultdict

from app.config import AppConfig, load_config

Message = dict[str, str]


class RateLimiter:
    def __init__(self, limit: int, window_sec: int = 60) -> None:
        self.limit = limit
        self.window_sec = window_sec
        self._hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str) -> bool:
        now = time.time()
        window_start = now - self.window_sec
        hits = [t for t in self._hits[key] if t > window_start]
        if len(hits) >= self.limit:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        return True

    def retry_after_sec(self, key: str) -> int:
        now = time.time()
        window_start = now - self.window_sec
        hits = [t for t in self._hits[key] if t > window_start]
        if not hits:
            return 0
        oldest = min(hits)
        return max(1, int(self.window_sec - (now - oldest)) + 1)


def _total_chars(messages: list[Message]) -> int:
    return sum(len(m.get("content", "")) for m in messages)


def _split_system(messages: list[Message]) -> tuple[list[Message], list[Message]]:
    system = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    return system, rest


def trim_messages(
    messages: list[Message],
    config: AppConfig | None = None,
) -> tuple[list[Message], bool]:
    """Обрезает историю: system сохраняется, старые пары user/assistant убираются."""
    cfg = config or load_config()
    if not messages:
        return [], False

    system, rest = _split_system(messages)
    trimmed = list(rest)
    changed = False

    while trimmed and (
        len(system) + len(trimmed) > cfg.max_messages
        or _total_chars(system + trimmed) > cfg.max_chars
    ):
        trimmed.pop(0)
        changed = True

    return system + trimmed, changed


def ensure_system_prompt(
    messages: list[Message],
    system_prompt: str,
) -> list[Message]:
    if any(m.get("role") == "system" for m in messages):
        return messages
    return [{"role": "system", "content": system_prompt}, *messages]
