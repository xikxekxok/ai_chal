"""Чат-агент с сохранением истории диалога в JSON между запусками."""

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


class ChatAgent:
    def __init__(
        self,
        config: AgentConfig,
        history_path: Path = DEFAULT_HISTORY_PATH,
    ) -> None:
        self._config = config
        self._history_path = history_path
        self._last_usage: dict[str, Any] = {}

        loaded = load_history(history_path)
        if loaded is not None:
            self._messages = loaded
        else:
            self._messages = [{"role": "system", "content": config.system_prompt}]

    @property
    def model(self) -> str:
        return self._config.model

    @property
    def last_usage(self) -> dict[str, Any]:
        return self._last_usage

    @property
    def message_count(self) -> int:
        return len(self._messages)

    @property
    def history_path(self) -> Path:
        return self._history_path

    def run(self, user_input: str) -> str:
        self._messages.append({"role": "user", "content": user_input})
        response = self._call_llm()
        self._messages.append({"role": "assistant", "content": response.content})
        self._last_usage = response.usage
        save_history(self._history_path, self._messages)
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
