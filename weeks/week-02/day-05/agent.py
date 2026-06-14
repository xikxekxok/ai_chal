"""Чат-агент с тремя стратегиями управления контекстом."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from context import ContextConfig, ContextStrategy, StrategyKind, StrategyStats, create_strategy
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

DEFAULT_MODEL = "deepseek/deepseek-v3.2"
DEFAULT_SYSTEM_PROMPT = (
    "Ты секретарь по сбору ТЗ для стартапа OpossumEats. "
    "Клиенты, разработчики и сотрудники — опоссумы. "
    "Режим: клиент диктует требования списком — по одному пункту за сообщение. "
    "Ты только кратко фиксируешь полученное (1–2 предложения): что записали. "
    "ЗАПРЕЩЕНО задавать вопросы, просить уточнения, предлагать обсудить следующий шаг "
    "или спрашивать «что дальше» — клиент сам пришлёт следующий пункт. "
    "На запрос «напомни…» — перечисли ранее зафиксированные факты. "
    "Можно одна короткая шутка про опossumов, не больше."
)
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
    extra_prompt_tokens: int = 0
    extra_completion_tokens: int = 0

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

    def record_extra(self, usage: dict[str, Any]) -> None:
        prompt = int(usage.get("prompt_tokens") or 0)
        completion = int(usage.get("completion_tokens") or 0)
        self.extra_prompt_tokens += prompt
        self.extra_completion_tokens += completion
        cost = (prompt * PRICE_IN_M + completion * PRICE_OUT_M) / 1_000_000
        self.session_cost_rub += cost
        self.session_prompt_tokens += prompt
        self.session_completion_tokens += completion

    def reset_session(self) -> None:
        self.prev_prompt_tokens = 0
        self.session_prompt_tokens = 0
        self.session_completion_tokens = 0
        self.session_cost_rub = 0.0
        self.extra_prompt_tokens = 0
        self.extra_completion_tokens = 0


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


def print_tokens(metrics: TurnMetrics, tracker: TokenTracker) -> None:
    extra = ""
    if tracker.extra_prompt_tokens:
        extra = f" | extra={tracker.extra_prompt_tokens} tok (facts)"
    print(
        f"[tokens] запрос={metrics.request_prompt_tokens} | "
        f"история={metrics.total_prompt_tokens} | "
        f"ответ={metrics.completion_tokens} | "
        f"₽={metrics.cost_rub:.4f} | "
        f"окно={metrics.context_pct:.1f}% | "
        f"сессия: {tracker.session_prompt_tokens} tok, ₽{tracker.session_cost_rub:.4f}{extra}"
    )


def print_strategy_stats(stats: StrategyStats) -> None:
    parts = [f"стратегия={stats.strategy}"]
    if stats.window_size:
        parts.append(f"окно={stats.window_size}")
    if stats.facts_count:
        parts.append(f"facts={stats.facts_count}")
    if stats.active_branch:
        parts.append(f"ветка={stats.active_branch}")
    if stats.branches:
        parts.append(f"ветки={stats.branches}")
    if stats.sent_messages:
        parts.append(f"в запросе={stats.sent_messages} msg")
    if stats.last_event:
        parts.append(stats.last_event)
    print(f"[context] {' | '.join(parts)}")


def print_facts(stats: StrategyStats) -> None:
    if stats.strategy != StrategyKind.FACTS.value or not stats.facts:
        return
    n = stats.facts_count
    label = "запись" if n == 1 else "записи" if 2 <= n <= 4 else "записей"
    print(f"[facts] {n} {label}:")
    for key, value in sorted(stats.facts.items()):
        print(f"  - {key}: {value}")


class ChatAgent:
    def __init__(
        self,
        config: AgentConfig,
        context_config: ContextConfig,
        history_path: Path = DEFAULT_HISTORY_PATH,
    ) -> None:
        self._config = config
        self._context_config = context_config
        self._history_path = history_path
        self._tracker = TokenTracker()
        self._last_metrics: TurnMetrics | None = None
        self._ctx: ContextStrategy = create_strategy(config.system_prompt, context_config)
        self._ctx.load_from_file(history_path)

    @property
    def model(self) -> str:
        return self._config.model

    @property
    def strategy(self) -> StrategyKind:
        return self._context_config.strategy

    @property
    def tracker(self) -> TokenTracker:
        return self._tracker

    @property
    def last_metrics(self) -> TurnMetrics | None:
        return self._last_metrics

    @property
    def message_count(self) -> int:
        return self._ctx.message_count

    @property
    def history_path(self) -> Path:
        return self._history_path

    @property
    def context_stats(self) -> StrategyStats:
        return self._ctx.stats()

    def reset_history(self) -> None:
        self._ctx.reset()
        if self._history_path.exists():
            self._history_path.unlink()

    def create_checkpoint(self) -> bool:
        return self._ctx.create_checkpoint()

    def fork_branches(self, name_a: str, name_b: str) -> bool:
        return self._ctx.fork_branches(name_a, name_b)

    def switch_branch(self, name: str) -> bool:
        return self._ctx.switch_branch(name)

    def run(self, user_input: str) -> str:
        messages = self._ctx.build_messages(user_input)
        content, _usage, metrics = self._complete_messages(messages)
        self._last_metrics = metrics
        prompt_after_turn = self._tracker.prev_prompt_tokens

        def side_effect_fn(msgs: list[dict[str, str]]) -> tuple[str, dict[str, Any]]:
            side_content, side_usage, _ = self._complete_messages(msgs)
            self._tracker.record_extra(side_usage)
            self._tracker.prev_prompt_tokens = prompt_after_turn
            return side_content, side_usage

        use_facts_fn = self._context_config.strategy == StrategyKind.FACTS
        complete_fn = side_effect_fn if use_facts_fn else None
        self._ctx.on_turn_complete(
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": content},
            complete_fn=complete_fn,
        )
        self._ctx.save_to_file(self._history_path)
        return content

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
