"""Простой чат-агент: инкапсулирует контекст и вызов LLM через Dockhost API."""

from __future__ import annotations

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


class ChatAgent:
    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self._messages: list[dict[str, str]] = [
            {"role": "system", "content": config.system_prompt},
        ]
        self._last_usage: dict[str, Any] = {}

    @property
    def model(self) -> str:
        return self._config.model

    @property
    def last_usage(self) -> dict[str, Any]:
        return self._last_usage

    def run(self, user_input: str) -> str:
        self._messages.append({"role": "user", "content": user_input})
        response = self._call_llm()
        self._messages.append({"role": "assistant", "content": response.content})
        self._last_usage = response.usage
        return response.content

    def _call_llm(self) -> AgentResponse:
        response = requests.post(
            f"{self._config.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._config.model,
                "messages": self._messages,
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        choice = data["choices"][0]
        content = choice["message"].get("content") or ""
        if not content:
            raise RuntimeError("LLM вернул пустой ответ.")
        return AgentResponse(content=content, usage=data.get("usage") or {})
