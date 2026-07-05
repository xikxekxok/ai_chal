"""Detailed per-run agent logs (one main.py invocation → one file in logs/)."""

from __future__ import annotations

import atexit
import json
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

from paths import LOGS_DIR

_log: RunLogger | None = None


def _truncate(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars] + "\n…", True


class RunLogger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: TextIO = path.open("w", encoding="utf-8")

    def close(self) -> None:
        if self._handle.closed:
            return
        self._write("=== END ===")
        self._handle.close()

    def _write(self, line: str = "") -> None:
        self._handle.write(line + "\n")
        self._handle.flush()

    def header(self, *, mode: str, **meta: Any) -> None:
        self._write(f"=== RUN {datetime.now().isoformat(timespec='seconds')} ===")
        self._write(f"mode: {mode}")
        for key, value in meta.items():
            self._write(f"{key}: {value}")
        self._write()

    def turn_start(self, turn_num: int, question_ru: str) -> None:
        self._write("=" * 60)
        self._write(f"TURN {turn_num}")
        self._write(f"user_ru: {question_ru}")
        self._write()

    def section(self, name: str) -> None:
        self._write(f"[{name}]")

    def line(self, text: str = "", *, indent: int = 0) -> None:
        self._write(f"{'  ' * indent}{text}")

    def kv(self, key: str, value: Any, *, indent: int = 0) -> None:
        self.line(f"{key}: {value}", indent=indent)

    def blank(self) -> None:
        self._write()

    def block(self, name: str, text: str, *, max_chars: int = 8000) -> None:
        self.section(name)
        body, truncated = _truncate(text, max_chars)
        if truncated:
            self.line(f"(truncated {len(text)} → {max_chars} chars)", indent=1)
        for item in body.splitlines():
            self.line(item, indent=1)
        self.blank()

    def json_block(self, name: str, data: Any) -> None:
        self.section(name)
        formatted = json.dumps(data, ensure_ascii=False, indent=2)
        for item in formatted.splitlines():
            self.line(item, indent=1)
        self.blank()

    def llm_messages(
        self,
        messages: list[dict[str, str]],
        *,
        max_chars: int = 16000,
    ) -> None:
        self.section("llm_messages")
        for index, message in enumerate(messages, start=1):
            role = message.get("role", "?")
            content = str(message.get("content", ""))
            self.line(
                f"--- {index}/{len(messages)} role={role} chars={len(content)} ---",
                indent=1,
            )
            body, truncated = _truncate(content, max_chars)
            if truncated:
                self.line(f"(truncated {len(content)} → {max_chars} chars)", indent=2)
            for item in body.splitlines() or [""]:
                self.line(item, indent=2)
        self.blank()

    def hits(self, name: str, hits: list[dict[str, Any]], *, limit: int = 25) -> None:
        self.section(name)
        if not hits:
            self.line("(none)", indent=1)
            self.blank()
            return
        for index, hit in enumerate(hits[:limit], start=1):
            chunk_id = hit.get("chunk_id", "?")
            title = str(hit.get("title", ""))[:60]
            section = str(hit.get("section", ""))[:40]
            parts = [f"{index}. chunk_id={chunk_id}"]
            embed = hit.get("score", hit.get("embed_score"))
            if embed is not None:
                parts.append(f"embed={float(embed):.4f}")
            rerank = hit.get("rerank_score")
            if rerank is not None:
                parts.append(f"rerank={float(rerank):.4f}")
            parts.append(f"title={title!r} section={section!r}")
            self.line(" ".join(parts), indent=1)
        if len(hits) > limit:
            self.line(f"... ещё {len(hits) - limit}", indent=1)
        self.blank()


class NullRunLogger:
    path: Path | None = None

    def close(self) -> None:
        return

    def header(self, *, mode: str, **meta: Any) -> None:
        return

    def turn_start(self, turn_num: int, question_ru: str) -> None:
        return

    def section(self, name: str) -> None:
        return

    def line(self, text: str = "", *, indent: int = 0) -> None:
        return

    def kv(self, key: str, value: Any, *, indent: int = 0) -> None:
        return

    def blank(self) -> None:
        return

    def block(self, name: str, text: str, *, max_chars: int = 8000) -> None:
        return

    def json_block(self, name: str, data: Any) -> None:
        return

    def llm_messages(
        self,
        messages: list[dict[str, str]],
        *,
        max_chars: int = 16000,
    ) -> None:
        return

    def hits(self, name: str, hits: list[dict[str, Any]], *, limit: int = 25) -> None:
        return


_NULL = NullRunLogger()


def init_run_log(mode: str, **meta: Any) -> RunLogger:
    global _log
    if _log is not None:
        _log.close()
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_mode = mode.replace("/", "-").replace(" ", "_")
    path = LOGS_DIR / f"{stamp}-{safe_mode}.log"
    _log = RunLogger(path)
    _log.header(mode=mode, **meta)
    atexit.register(close_run_log)
    return _log


def get_run_log() -> RunLogger | NullRunLogger:
    return _log if _log is not None else _NULL


def close_run_log() -> None:
    global _log
    if _log is not None:
        _log.close()
        _log = None
