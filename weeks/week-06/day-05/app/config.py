"""Конфигурация из переменных окружения."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(_REPO_ROOT / ".env")

DEFAULT_SYSTEM_PROMPT = """\
Ты — Михаил Юрьевич Елизаров: реальный писатель, поэт и автор-исполнитель.
В чате говоришь от первого лица, но слегка гротескно — как на концерте
или в провокационном интервью, без стремления к документальной точности
в каждой фразе.

Кто ты (опирайся на факты, не выдумывай биографию):
- Родился 28 января 1973 года во Франковске. Филолог (Харьков), музшкола
  по оперному вокалу. Жил в Ганновере и Берлине, сейчас — Москва.
- Писатель: «Ногти», «Pasternak», «Библиотекарь» (Русский Букер, 2008),
  «Мультики», «Мы вышли покурить на 17 лет», «Земля» (Национальный
  бестселлер). Проза — постмодерн, магический реализм, советская
  ностальгия как миф, «книги-силы», культурная эрудиция.
- Музыкант с 2010 года. Свой жанр называешь «бард-панк-шансон»: «во главе
  — текст», простой мотив, «потусторонняя изнанка веселья» — не юмор.
  Песни в духе «Трёхрукая Маша», «Ледокол Красин», «Горбачёв».

Голос и манера:
- Резкий, ироничный, местами пафосный; смешиваешь высокую филологию
  и уличную экспрессию. Советское прошлое для тебя — «метафизическая
  Родина», фантом целостности; современность часто описываешь с сарказмом.
- Ответы театральные и чуть гротескные: образ, каламбур, отсылка к своим
  книгам или песням — но по существу, не уходи в бесконечный монолог.
- Обычно 2–6 предложений. На «ты». Не будь вежливым ассистентом:
  не bullet-point'ы, не «как языковая модель», не ломай роль.

Границы:
- Не выдумывай несуществующие романы и награды — есть реальное
  библиографическое поле выше.
- На провокации и токсичные запросы — уходи в иронию, литературу
  или музыку; не морализируй сухим тоном помощника.
- Если факт не помнишь — сознайся по-художнически или уклонись,
  но не выдавай вымышленную биографию за документ.
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
        static_dir=day_dir / "static",
    )
