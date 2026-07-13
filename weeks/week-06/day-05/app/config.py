"""Конфигурация из переменных окружения."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(_REPO_ROOT / ".env")


class JokeTheme(TypedDict):
    id: str
    label: str


OPPOSSUM_JOKE_THEMES: list[JokeTheme] = [
    {"id": "dead_play", "label": "Притворство мёртвым"},
    {"id": "trash_can", "label": "Ночной поход к мусорному баку"},
    {"id": "tail_story", "label": "Хвост, который живёт своей жизнью"},
    {"id": "programmer", "label": "Опоссум-программист"},
    {"id": "neighbor_cat", "label": "Война с соседским котом"},
    {"id": "rock_fest", "label": "Опоссум на рок-фестивале"},
    {"id": "crossing", "label": "Переход дороги ночью"},
    {"id": "office", "label": "Опоссум в open space"},
    {"id": "attic", "label": "Зимовка на чердаке"},
    {"id": "takeaway", "label": "Еда на вынос"},
]

DEFAULT_SYSTEM_PROMPT = """\
Ты — автор коротких анекдотов про опоссумов на русском языке.

Правила:
- Пиши один анекдот из 2–5 предложений: добрый абсурд, лёгкая самоирония.
- Если пользователь указал несколько тем — вплети все в один сюжет.
- Не начинай с «Вот анекдот» и не добавляй мораль в конце.
- Не ломай четвёртую стену и не обращайся к читателю напрямую.
- Отвечай только текстом анекдота, без пояснений и заголовков.
"""


@dataclass(frozen=True)
class AppConfig:
    host: str
    port: int
    ollama_base_url: str
    ollama_model: str
    ollama_think: bool
    cloud_base_url: str
    cloud_model: str
    cloud_api_key: str
    system_prompt: str
    rate_limit_per_min: int
    max_messages: int
    max_chars: int
    max_tokens: int
    num_ctx: int
    ollama_max_predict: int
    ollama_temperature: float
    static_dir: Path


def load_config() -> AppConfig:
    think_raw = os.environ.get("OLLAMA_THINK", "false").lower()
    day_dir = Path(__file__).resolve().parents[1]
    cloud_key = os.environ.get("DOCKHOST_AI_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    return AppConfig(
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8080")),
        ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip(
            "/"
        ),
        ollama_model=os.environ.get("OLLAMA_CHAT_MODEL", "qwen3:4b"),
        ollama_think=think_raw in {"1", "true", "yes"},
        cloud_base_url=os.environ.get(
            "OPENAI_BASE_URL", "https://inference.dockhost.io/v1"
        ).rstrip("/"),
        cloud_model=os.environ.get("DOCKHOST_MODEL", "deepseek/deepseek-v3.2"),
        cloud_api_key=cloud_key,
        system_prompt=os.environ.get("CHAT_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
        rate_limit_per_min=int(os.environ.get("CHAT_RATE_LIMIT", "10")),
        max_messages=int(os.environ.get("CHAT_MAX_MESSAGES", "40")),
        max_chars=int(os.environ.get("CHAT_MAX_CHARS", "12000")),
        max_tokens=int(os.environ.get("CHAT_MAX_TOKENS", "2048")),
        num_ctx=int(os.environ.get("CHAT_NUM_CTX", "4096")),
        ollama_max_predict=int(os.environ.get("OLLAMA_MAX_PREDICT", "0")),
        ollama_temperature=float(os.environ.get("OLLAMA_TEMPERATURE", "1.0")),
        static_dir=day_dir / "static",
    )
