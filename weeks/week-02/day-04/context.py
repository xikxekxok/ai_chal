"""Управление контекстом: summary + последние N сообщений."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SUMMARY_ACK = "Понял, учту при ответах."
SUMMARY_USER_PREFIX = "Краткое содержание предыдущего диалога:\n"
SUMMARIZE_SYSTEM = (
    "Сожми фрагмент диалога в краткое summary на русском. "
    "Сохрани факты, числа, шутки и ключевые детали. Без воды, 5–10 предложений."
)


@dataclass
class CompressionConfig:
    keep_recent: int = 6
    compress_every: int = 10
    enabled: bool = True


@dataclass
class CompressionStats:
    archive_pending: int = 0
    summary_chars: int = 0
    recent_count: int = 0
    compress_events: int = 0
    summarize_prompt_tokens: int = 0
    summarize_completion_tokens: int = 0
    last_event: str = ""


@dataclass
class ContextState:
    summary: str | None = None
    full_log: list[dict[str, str]] = field(default_factory=list)
    archive_pending: list[dict[str, str]] = field(default_factory=list)
    recent: list[dict[str, str]] = field(default_factory=list)


CompleteFn = Callable[[list[dict[str, str]]], tuple[str, dict[str, Any]]]


class ContextManager:
    def __init__(
        self,
        system_prompt: str,
        config: CompressionConfig | None = None,
    ) -> None:
        self._system_prompt = system_prompt
        self._config = config or CompressionConfig()
        self._state = ContextState()
        self._compress_events = 0
        self._summarize_prompt_tokens = 0
        self._summarize_completion_tokens = 0
        self._last_event = ""
        self._summary_created_this_turn: str | None = None

    @property
    def config(self) -> CompressionConfig:
        return self._config

    @property
    def summary(self) -> str | None:
        return self._state.summary

    @property
    def message_count(self) -> int:
        return 1 + len(self._state.full_log)

    def pop_summary_created(self) -> str | None:
        """Текст summary, созданного на последнем ходе (один раз)."""
        created = self._summary_created_this_turn
        self._summary_created_this_turn = None
        return created

    @property
    def stats(self) -> CompressionStats:
        return CompressionStats(
            archive_pending=len(self._state.archive_pending),
            summary_chars=len(self._state.summary or ""),
            recent_count=len(self._state.recent),
            compress_events=self._compress_events,
            summarize_prompt_tokens=self._summarize_prompt_tokens,
            summarize_completion_tokens=self._summarize_completion_tokens,
            last_event=self._last_event,
        )

    def load_from_file(self, path: Path) -> bool:
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False

        messages = data.get("messages")
        if not isinstance(messages, list) or not messages:
            return False

        non_system = [m for m in messages if m.get("role") != "system"]
        self._state = ContextState(
            summary=data.get("summary"),
            full_log=list(non_system),
        )
        if self._config.enabled:
            self._rebuild_compression_state()
        else:
            self._state.recent = []
            self._state.archive_pending = []
        return True

    def save_to_file(self, path: Path) -> None:
        payload = {
            "summary": self._state.summary,
            "messages": [
                {"role": "system", "content": self._system_prompt},
                *self._state.full_log,
            ],
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def reset(self) -> None:
        self._state = ContextState()
        self._compress_events = 0
        self._summarize_prompt_tokens = 0
        self._summarize_completion_tokens = 0
        self._last_event = ""
        self._summary_created_this_turn = None

    def build_messages(self, user_input: str) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._system_prompt},
        ]
        if self._config.enabled:
            if self._state.summary:
                messages.append(
                    {
                        "role": "user",
                        "content": f"{SUMMARY_USER_PREFIX}{self._state.summary}",
                    }
                )
                messages.append({"role": "assistant", "content": SUMMARY_ACK})
            messages.extend(self._state.recent)
        else:
            messages.extend(self._state.full_log)
        messages.append({"role": "user", "content": user_input})
        return messages

    def on_turn_complete(
        self,
        user_msg: dict[str, str],
        assistant_msg: dict[str, str],
        *,
        complete_fn: CompleteFn | None = None,
    ) -> None:
        self._state.full_log.extend([user_msg, assistant_msg])
        if not self._config.enabled:
            self._last_event = "сжатие выкл"
            return

        self._state.recent.extend([user_msg, assistant_msg])
        self._trim_recent_to_keep()

        if complete_fn is not None:
            self._maybe_compress(complete_fn)

    def _rebuild_compression_state(self) -> None:
        """Восстановить recent/archive из full_log после загрузки."""
        keep = self._config.keep_recent
        if self._state.summary:
            self._state.recent = (
                self._state.full_log[-keep:]
                if len(self._state.full_log) > keep
                else list(self._state.full_log)
            )
            self._state.archive_pending = []
        else:
            self._state.recent = list(self._state.full_log)
            self._state.archive_pending = []
            self._trim_recent_to_keep()

    def _trim_recent_to_keep(self) -> None:
        keep = self._config.keep_recent
        while len(self._state.recent) > keep:
            self._state.archive_pending.append(self._state.recent.pop(0))

    def _maybe_compress(self, complete_fn: CompleteFn) -> None:
        while len(self._state.archive_pending) >= self._config.compress_every:
            batch = self._state.archive_pending[: self._config.compress_every]
            self._state.archive_pending = self._state.archive_pending[
                self._config.compress_every :
            ]
            new_summary, usage = self._summarize_batch(batch, complete_fn)
            self._state.summary = new_summary
            self._summary_created_this_turn = new_summary
            self._compress_events += 1
            self._summarize_prompt_tokens += int(usage.get("prompt_tokens") or 0)
            self._summarize_completion_tokens += int(usage.get("completion_tokens") or 0)
            self._last_event = (
                f"сжато +{len(batch)} → summary ({len(new_summary)} sym)"
            )

    def _summarize_batch(
        self,
        batch: list[dict[str, str]],
        complete_fn: CompleteFn,
    ) -> tuple[str, dict[str, Any]]:
        lines: list[str] = []
        for msg in batch:
            role_label = "Пользователь" if msg["role"] == "user" else "Ассистент"
            lines.append(f"{role_label}: {msg['content']}")
        block = "\n".join(lines)

        if self._state.summary:
            user_content = (
                f"Уже есть summary:\n{self._state.summary}\n\n"
                f"Новый фрагмент для слияния:\n{block}\n\n"
                "Обнови summary одним связным текстом."
            )
        else:
            user_content = f"Сожми диалог:\n{block}"

        messages = [
            {"role": "system", "content": SUMMARIZE_SYSTEM},
            {"role": "user", "content": user_content},
        ]
        content, usage = complete_fn(messages)
        if not content.strip():
            raise RuntimeError("Summarize вернул пустой ответ.")
        return content.strip(), usage
