"""Чат-агент с историей диалога в памяти и вызовом локальной LLM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from llm import OllamaConfig, complete_local, load_ollama_config

DEFAULT_SYSTEM_PROMPT = "Ты полезный ассистент. Отвечай кратко на русском."


@dataclass
class AgentConfig:
    ollama: OllamaConfig
    system_prompt: str = DEFAULT_SYSTEM_PROMPT


def load_agent_config() -> AgentConfig:
    return AgentConfig(ollama=load_ollama_config())


class ChatAgent:
    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self._messages: list[dict[str, str]] = [
            {"role": "system", "content": config.system_prompt},
        ]
        self._last_usage: dict[str, Any] = {}
        self._last_latency_ms: int = 0

    @property
    def model(self) -> str:
        return self._config.ollama.model

    @property
    def last_usage(self) -> dict[str, Any]:
        return self._last_usage

    @property
    def last_latency_ms(self) -> int:
        return self._last_latency_ms

    @property
    def message_count(self) -> int:
        return len(self._messages)

    def run(self, user_input: str) -> str:
        self._messages.append({"role": "user", "content": user_input})
        result = complete_local(self._messages, self._config.ollama)
        self._messages.append({"role": "assistant", "content": result.content})
        self._last_usage = result.usage
        self._last_latency_ms = result.latency_ms
        return result.content
