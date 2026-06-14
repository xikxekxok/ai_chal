"""Три стратегии управления контекстом: sliding window, facts, branching."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

CompleteFn = Callable[[list[dict[str, str]]], tuple[str, dict[str, Any]]]

FACTS_ACK = "Понял, учту эти факты."
FACTS_USER_PREFIX = "Известные факты из диалога (ключ → значение):\n"
FACTS_UPDATE_SYSTEM = (
    "Извлеки из диалога важные факты: цель, ограничения, предпочтения, решения, договорённости. "
    'Верни JSON-объект {"ключ": "значение", ...}. '
    "Обнови существующие факты новой информацией. Только JSON, без markdown."
)


class StrategyKind(StrEnum):
    SLIDING = "sliding"
    FACTS = "facts"
    BRANCHING = "branching"


@dataclass
class ContextConfig:
    window_size: int = 6
    strategy: StrategyKind = StrategyKind.SLIDING


@dataclass
class StrategyStats:
    strategy: str
    window_size: int = 0
    stored_messages: int = 0
    sent_messages: int = 0
    facts_count: int = 0
    facts: dict[str, str] = field(default_factory=dict)
    facts_delta: str = ""
    facts_update_tokens: int = 0
    active_branch: str | None = None
    branches: list[str] = field(default_factory=list)
    checkpoint_at: int | None = None
    last_event: str = ""


class ContextStrategy(ABC):
    def __init__(self, system_prompt: str, config: ContextConfig) -> None:
        self._system_prompt = system_prompt
        self._config = config
        self._last_event = ""

    @property
    @abstractmethod
    def kind(self) -> StrategyKind: ...

    @property
    def message_count(self) -> int:
        return 1 + self._stored_turns()

    @abstractmethod
    def _stored_turns(self) -> int: ...

    @abstractmethod
    def build_messages(self, user_input: str) -> list[dict[str, str]]: ...

    @abstractmethod
    def on_turn_complete(
        self,
        user_msg: dict[str, str],
        assistant_msg: dict[str, str],
        *,
        complete_fn: CompleteFn | None = None,
    ) -> None: ...

    @abstractmethod
    def reset(self) -> None: ...

    @abstractmethod
    def load_from_file(self, path: Path) -> bool: ...

    @abstractmethod
    def save_to_file(self, path: Path) -> None: ...

    @abstractmethod
    def stats(self) -> StrategyStats: ...

    def create_checkpoint(self) -> bool:
        return False

    def fork_branches(self, name_a: str, name_b: str) -> bool:
        return False

    def switch_branch(self, name: str) -> bool:
        return False


class SlidingWindowStrategy(ContextStrategy):
    """Стратегия 1: только последние N сообщений."""

    def __init__(self, system_prompt: str, config: ContextConfig) -> None:
        super().__init__(system_prompt, config)
        self._messages: list[dict[str, str]] = []

    @property
    def kind(self) -> StrategyKind:
        return StrategyKind.SLIDING

    def _stored_turns(self) -> int:
        return len(self._messages)

    def _window(self) -> list[dict[str, str]]:
        n = self._config.window_size
        if n <= 0:
            return list(self._messages)
        return self._messages[-n:]

    def build_messages(self, user_input: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self._system_prompt},
            *self._window(),
            {"role": "user", "content": user_input},
        ]

    def on_turn_complete(
        self,
        user_msg: dict[str, str],
        assistant_msg: dict[str, str],
        *,
        complete_fn: CompleteFn | None = None,
    ) -> None:
        self._messages.extend([user_msg, assistant_msg])
        n = self._config.window_size
        if n > 0 and len(self._messages) > n:
            dropped = len(self._messages) - n
            self._messages = self._messages[-n:]
            self._last_event = f"отброшено {dropped} старых сообщений (окно={n})"
        else:
            self._last_event = f"окно={n}, хранится {len(self._messages)} сообщений"

    def reset(self) -> None:
        self._messages = []
        self._last_event = ""

    def load_from_file(self, path: Path) -> bool:
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False
        messages = data.get("messages")
        if not isinstance(messages, list):
            return False
        self._messages = [m for m in messages if m.get("role") != "system"]
        n = self._config.window_size
        if n > 0 and len(self._messages) > n:
            self._messages = self._messages[-n:]
        return True

    def save_to_file(self, path: Path) -> None:
        payload = {
            "strategy": self.kind.value,
            "window_size": self._config.window_size,
            "messages": [
                {"role": "system", "content": self._system_prompt},
                *self._messages,
            ],
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def stats(self) -> StrategyStats:
        window = self._window()
        return StrategyStats(
            strategy=self.kind.value,
            window_size=self._config.window_size,
            stored_messages=len(self._messages),
            sent_messages=len(window),
            last_event=self._last_event,
        )


class FactsStrategy(ContextStrategy):
    """Стратегия 2: блок facts (ключ-значение) + последние N сообщений."""

    def __init__(self, system_prompt: str, config: ContextConfig) -> None:
        super().__init__(system_prompt, config)
        self._messages: list[dict[str, str]] = []
        self._facts: dict[str, str] = {}
        self._facts_update_tokens = 0
        self._facts_delta = ""

    @property
    def kind(self) -> StrategyKind:
        return StrategyKind.FACTS

    def _stored_turns(self) -> int:
        return len(self._messages)

    def _window(self) -> list[dict[str, str]]:
        n = self._config.window_size
        if n <= 0:
            return list(self._messages)
        return self._messages[-n:]

    def format_facts(self) -> str:
        if not self._facts:
            return "(пока пусто)"
        lines = [f"- {key}: {value}" for key, value in sorted(self._facts.items())]
        return "\n".join(lines)

    def build_messages(self, user_input: str) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._system_prompt},
        ]
        if self._facts:
            messages.append(
                {
                    "role": "user",
                    "content": f"{FACTS_USER_PREFIX}{self.format_facts()}",
                }
            )
            messages.append({"role": "assistant", "content": FACTS_ACK})
        messages.extend(self._window())
        messages.append({"role": "user", "content": user_input})
        return messages

    def on_turn_complete(
        self,
        user_msg: dict[str, str],
        assistant_msg: dict[str, str],
        *,
        complete_fn: CompleteFn | None = None,
    ) -> None:
        if complete_fn is not None:
            self._update_facts(user_msg, complete_fn)
        self._messages.extend([user_msg, assistant_msg])
        n = self._config.window_size
        if n > 0 and len(self._messages) > n:
            self._messages = self._messages[-n:]
        delta_note = f", {self._facts_delta}" if self._facts_delta else ""
        self._last_event = (
            f"facts={len(self._facts)}, recent={len(self._messages)}, "
            f"окно={self._config.window_size}{delta_note}"
        )

    def _update_facts(self, user_msg: dict[str, str], complete_fn: CompleteFn) -> None:
        before = set(self._facts.keys())
        existing = json.dumps(self._facts, ensure_ascii=False) if self._facts else "{}"
        recent = self._messages[-4:] if self._messages else []
        context_lines = []
        for msg in recent:
            role = "Пользователь" if msg["role"] == "user" else "Ассистент"
            context_lines.append(f"{role}: {msg['content']}")
        context_block = "\n".join(context_lines) if context_lines else "(нет)"

        update_messages = [
            {"role": "system", "content": FACTS_UPDATE_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Текущие факты:\n{existing}\n\n"
                    f"Контекст:\n{context_block}\n\n"
                    f"Новое сообщение пользователя:\n{user_msg['content']}\n\n"
                    "Обнови JSON фактов."
                ),
            },
        ]
        content, usage = complete_fn(update_messages)
        self._facts_update_tokens += int(usage.get("prompt_tokens") or 0)
        self._facts_update_tokens += int(usage.get("completion_tokens") or 0)
        try:
            cleaned = content.strip().removeprefix("```json").removesuffix("```").strip()
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                for key, value in parsed.items():
                    if key and value is not None:
                        self._facts[str(key)] = str(value)
        except json.JSONDecodeError:
            self._facts_delta = "parse error"
            return

        after = set(self._facts.keys())
        new_keys = after - before
        updated = before & after
        parts = []
        if new_keys:
            parts.append(f"+{len(new_keys)} новых")
        if updated:
            parts.append(f"~{len(updated)} обновлено")
        self._facts_delta = ", ".join(parts) if parts else ""

    def reset(self) -> None:
        self._messages = []
        self._facts = {}
        self._facts_update_tokens = 0
        self._facts_delta = ""
        self._last_event = ""

    def load_from_file(self, path: Path) -> bool:
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False
        messages = data.get("messages")
        if not isinstance(messages, list):
            return False
        self._messages = [m for m in messages if m.get("role") != "system"]
        facts = data.get("facts")
        self._facts = {str(k): str(v) for k, v in facts.items()} if isinstance(facts, dict) else {}
        n = self._config.window_size
        if n > 0 and len(self._messages) > n:
            self._messages = self._messages[-n:]
        return True

    def save_to_file(self, path: Path) -> None:
        payload = {
            "strategy": self.kind.value,
            "window_size": self._config.window_size,
            "facts": self._facts,
            "messages": [
                {"role": "system", "content": self._system_prompt},
                *self._messages,
            ],
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def stats(self) -> StrategyStats:
        return StrategyStats(
            strategy=self.kind.value,
            window_size=self._config.window_size,
            stored_messages=len(self._messages),
            sent_messages=len(self._window()) + (2 if self._facts else 0),
            facts_count=len(self._facts),
            facts=dict(self._facts),
            facts_delta=self._facts_delta,
            facts_update_tokens=self._facts_update_tokens,
            last_event=self._last_event,
        )


class BranchingStrategy(ContextStrategy):
    """Стратегия 3: checkpoint + независимые ветки диалога."""

    def __init__(self, system_prompt: str, config: ContextConfig) -> None:
        super().__init__(system_prompt, config)
        self._shared: list[dict[str, str]] = []
        self._branches: dict[str, list[dict[str, str]]] = {}
        self._active_branch: str | None = None
        self._checkpoint_at: int | None = None

    @property
    def kind(self) -> StrategyKind:
        return StrategyKind.BRANCHING

    def _stored_turns(self) -> int:
        branch_msgs = self._branches.get(self._active_branch or "", [])
        return len(self._shared) + len(branch_msgs)

    def _active_messages(self) -> list[dict[str, str]]:
        if self._active_branch and self._active_branch in self._branches:
            return self._shared + self._branches[self._active_branch]
        return list(self._shared)

    def build_messages(self, user_input: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self._system_prompt},
            *self._active_messages(),
            {"role": "user", "content": user_input},
        ]

    def on_turn_complete(
        self,
        user_msg: dict[str, str],
        assistant_msg: dict[str, str],
        *,
        complete_fn: CompleteFn | None = None,
    ) -> None:
        pair = [user_msg, assistant_msg]
        if self._active_branch and self._active_branch in self._branches:
            self._branches[self._active_branch].extend(pair)
        else:
            self._shared.extend(pair)
        self._last_event = (
            f"ветка={self._active_branch or 'main'}, "
            f"shared={len(self._shared)}, "
            f"branches={list(self._branches)}"
        )

    def create_checkpoint(self) -> bool:
        self._checkpoint_at = len(self._shared)
        self._last_event = f"checkpoint на сообщении {self._checkpoint_at}"
        return True

    def fork_branches(self, name_a: str, name_b: str) -> bool:
        if self._checkpoint_at is None:
            self._checkpoint_at = len(self._shared)
        self._shared = self._shared[: self._checkpoint_at]
        self._branches = {name_a: [], name_b: []}
        self._active_branch = name_a
        self._last_event = f"fork → {name_a}, {name_b} от checkpoint={self._checkpoint_at}"
        return True

    def switch_branch(self, name: str) -> bool:
        if name not in self._branches:
            return False
        self._active_branch = name
        self._last_event = f"переключено на ветку {name}"
        return True

    def reset(self) -> None:
        self._shared = []
        self._branches = {}
        self._active_branch = None
        self._checkpoint_at = None
        self._last_event = ""

    def load_from_file(self, path: Path) -> bool:
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False
        shared = data.get("shared")
        branches = data.get("branches")
        if not isinstance(shared, list) or not isinstance(branches, dict):
            return False
        self._shared = list(shared)
        self._branches = {
            str(name): list(msgs) for name, msgs in branches.items() if isinstance(msgs, list)
        }
        active = data.get("active_branch")
        self._active_branch = str(active) if active else None
        self._checkpoint_at = data.get("checkpoint_at")
        return True

    def save_to_file(self, path: Path) -> None:
        payload = {
            "strategy": self.kind.value,
            "checkpoint_at": self._checkpoint_at,
            "active_branch": self._active_branch,
            "shared": self._shared,
            "branches": self._branches,
            "messages": [
                {"role": "system", "content": self._system_prompt},
                *self._active_messages(),
            ],
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def stats(self) -> StrategyStats:
        active = self._active_messages()
        return StrategyStats(
            strategy=self.kind.value,
            stored_messages=len(active),
            sent_messages=len(active),
            active_branch=self._active_branch,
            branches=list(self._branches),
            checkpoint_at=self._checkpoint_at,
            last_event=self._last_event,
        )


def create_strategy(system_prompt: str, config: ContextConfig) -> ContextStrategy:
    if config.strategy == StrategyKind.SLIDING:
        return SlidingWindowStrategy(system_prompt, config)
    if config.strategy == StrategyKind.FACTS:
        return FactsStrategy(system_prompt, config)
    if config.strategy == StrategyKind.BRANCHING:
        return BranchingStrategy(system_prompt, config)
    raise ValueError(f"Unknown strategy: {config.strategy}")
