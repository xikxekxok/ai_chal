from __future__ import annotations

import time


def format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m{secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


class StageTimer:
    def __init__(self) -> None:
        self._started = time.monotonic()

    def elapsed(self) -> float:
        return time.monotonic() - self._started

    def elapsed_str(self) -> str:
        return format_duration(self.elapsed())


class EmbedProgress:
    def __init__(self, total: int) -> None:
        self.total = total
        self.current = 0
        self._timer = StageTimer()
        self._last_print = 0.0
        self._chunk_times: list[float] = []
        self._last_chunk_at = self._timer.elapsed()

    def tick(self) -> None:
        now = self._timer.elapsed()
        if self.current > 0:
            self._chunk_times.append(now - self._last_chunk_at)
            if len(self._chunk_times) > 20:
                self._chunk_times.pop(0)
        self._last_chunk_at = now
        self.current += 1

    def _eta_seconds(self) -> float | None:
        if self.current < 5 or not self._chunk_times:
            return None
        avg = sum(self._chunk_times) / len(self._chunk_times)
        remaining = self.total - self.current
        return avg * remaining

    def format_line(self) -> str:
        pct = int(self.current / self.total * 100) if self.total else 0
        line = f"{self.current}/{self.total} ({pct}%) elapsed {self._timer.elapsed_str()}"
        eta = self._eta_seconds()
        if eta is not None:
            line += f" ETA ~{format_duration(eta)}"
        return line

    def maybe_print(self, force: bool = False) -> None:
        now = time.monotonic()
        if force or self.current >= self.total:
            print(self.format_line(), flush=True)
            self._last_print = now
            return
        if self.current % 10 == 0 or now - self._last_print >= 30:
            print(self.format_line(), flush=True)
            self._last_print = now
