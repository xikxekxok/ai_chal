"""Чат-агент с подсчётом токенов, стоимости и stateless complete() для recall-демо."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

DEFAULT_MODEL = "deepseek/deepseek-v3.2"
DEFAULT_SYSTEM_PROMPT = "Ты полезный ассистент. Отвечай кратко на русском."
DEFAULT_HISTORY_PATH = Path(__file__).parent / "chat_history.json"

MODEL_CONTEXT_LIMIT = 131_072
PRICE_IN_M = 35.0
PRICE_OUT_M = 51.0


class ContextOverflowError(Exception):
    """Контекст превысил лимит модели (HTTP 400)."""


@dataclass
class AgentConfig:
    api_key: str
    base_url: str
    model: str
    system_prompt: str = DEFAULT_SYSTEM_PROMPT


@dataclass
class AgentResponse:
    content: str
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnMetrics:
    request_prompt_tokens: int
    total_prompt_tokens: int
    completion_tokens: int
    cost_rub: float
    context_pct: float


@dataclass
class TokenTracker:
    prev_prompt_tokens: int = 0
    session_prompt_tokens: int = 0
    session_completion_tokens: int = 0
    session_cost_rub: float = 0.0

    def record(self, usage: dict[str, Any]) -> TurnMetrics:
        prompt = int(usage.get("prompt_tokens") or 0)
        completion = int(usage.get("completion_tokens") or 0)
        request_delta = max(prompt - self.prev_prompt_tokens, 0)
        cost = (prompt * PRICE_IN_M + completion * PRICE_OUT_M) / 1_000_000
        context_pct = prompt / MODEL_CONTEXT_LIMIT * 100 if MODEL_CONTEXT_LIMIT else 0.0

        self.prev_prompt_tokens = prompt
        self.session_prompt_tokens += prompt
        self.session_completion_tokens += completion
        self.session_cost_rub += cost

        return TurnMetrics(
            request_prompt_tokens=request_delta,
            total_prompt_tokens=prompt,
            completion_tokens=completion,
            cost_rub=cost,
            context_pct=context_pct,
        )


def load_agent_config() -> AgentConfig:
    api_key = os.environ.get("DOCKHOST_AI_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print(
            "Задайте DOCKHOST_AI_KEY в .env (см. .env.example в корне репозитория).",
            file=sys.stderr,
        )
        sys.exit(1)

    base_url = os.environ.get("OPENAI_BASE_URL", "https://inference.dockhost.io/v1").rstrip("/")
    model = os.environ.get("DOCKHOST_MODEL", DEFAULT_MODEL)
    return AgentConfig(api_key=api_key, base_url=base_url, model=model)


def load_history(path: Path) -> list[dict[str, str]] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[store] не удалось прочитать {path.name}: {exc}", file=sys.stderr)
        return None
    messages = data.get("messages")
    if not isinstance(messages, list) or not messages:
        print(f"[store] пустая или неверная история в {path.name}", file=sys.stderr)
        return None
    return messages


def save_history(path: Path, messages: list[dict[str, str]]) -> None:
    path.write_text(
        json.dumps({"messages": messages}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def print_tokens(metrics: TurnMetrics, tracker: TokenTracker) -> None:
    print(
        f"[tokens] запрос={metrics.request_prompt_tokens} | "
        f"история={metrics.total_prompt_tokens} | "
        f"ответ={metrics.completion_tokens} | "
        f"₽={metrics.cost_rub:.4f} | "
        f"окно={metrics.context_pct:.1f}% | "
        f"сессия: {tracker.session_prompt_tokens} tok, ₽{tracker.session_cost_rub:.4f}"
    )


class ChatAgent:
    def __init__(
        self,
        config: AgentConfig,
        history_path: Path = DEFAULT_HISTORY_PATH,
    ) -> None:
        self._config = config
        self._history_path = history_path
        self._tracker = TokenTracker()
        self._last_metrics: TurnMetrics | None = None

        loaded = load_history(history_path)
        if loaded is not None:
            self._messages = loaded
        else:
            self._messages = [{"role": "system", "content": config.system_prompt}]

    @property
    def model(self) -> str:
        return self._config.model

    @property
    def tracker(self) -> TokenTracker:
        return self._tracker

    @property
    def last_metrics(self) -> TurnMetrics | None:
        return self._last_metrics

    @property
    def message_count(self) -> int:
        return len(self._messages)

    @property
    def history_path(self) -> Path:
        return self._history_path

    def run(self, user_input: str) -> str:
        self._messages.append({"role": "user", "content": user_input})
        content, _usage, metrics = self._complete_messages(self._messages)
        self._messages.append({"role": "assistant", "content": content})
        self._last_metrics = metrics
        save_history(self._history_path, self._messages)
        return content

    def complete(self, messages: list[dict[str, str]]) -> tuple[str, dict[str, Any], TurnMetrics]:
        """Stateless вызов: не мутирует внутреннюю историю агента."""
        self._tracker.prev_prompt_tokens = 0
        content, usage, metrics = self._complete_messages(messages)
        self._last_metrics = metrics
        return content, usage, metrics

    def _complete_messages(
        self, messages: list[dict[str, str]]
    ) -> tuple[str, dict[str, Any], TurnMetrics]:
        response = requests.post(
            f"{self._config.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._config.model,
                "messages": messages,
            },
            timeout=300,
        )
        if response.status_code == 400:
            detail = response.text[:300]
            raise ContextOverflowError(f"HTTP 400 — контекст переполнен: {detail}")
        response.raise_for_status()

        data = response.json()
        choice = data["choices"][0]
        content = choice["message"].get("content") or ""
        if not content:
            raise RuntimeError("LLM вернул пустой ответ.")
        usage = data.get("usage") or {}
        metrics = self._tracker.record(usage)
        return content, usage, metrics
