"""Second brain pipelines: enrich/save, expand/ask, search."""

from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass
from typing import Any

from db import get_connection
from llm import LlmConfig, UsageTracker, complete_text, try_load_llm_config
from pack import build_ask_messages, pack_context
from retrieve import RetrieveResult, notes_from_hits, retrieve
from store import NoteRecord, insert_note

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


@dataclass
class SaveResult:
    note: NoteRecord
    n_chunks: int
    n_embedded: int
    enriched: bool


@dataclass
class AskResult:
    answer: str
    retrieve: RetrieveResult
    note_cards: list[dict[str, Any]]
    pack_chars: int
    llm_ms: float
    tracker: UsageTracker


def _extract_json(text: str) -> dict[str, Any] | None:
    raw = text.strip()
    m = _JSON_FENCE.search(raw)
    if m:
        raw = m.group(1).strip()
    # try whole text, then first {...}
    for candidate in (raw,):
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            return None
    return None


def _preview(text: str, n: int = 80) -> str:
    one = " ".join(text.split())
    if len(one) <= n:
        return one
    return one[: n - 1] + "…"


def enrich_note(
    text: str,
    *,
    config: LlmConfig | None,
    tracker: UsageTracker | None = None,
) -> dict[str, Any] | None:
    if config is None:
        return None
    messages = [
        {
            "role": "system",
            "content": (
                "Ты помогаешь структурировать заметку для personal knowledge base. "
                "Верни ТОЛЬКО JSON-объект с ключами: "
                "title (короткий заголовок), tags (массив строк), "
                "aliases (синонимы и альтернативные формулировки для поиска), "
                "summary (1–3 предложения), body (очищенный/чуть структурированный текст заметки). "
                "Язык — как у исходного текста."
            ),
        },
        {
            "role": "user",
            "content": f"Заметка:\n\n{text}",
        },
    ]
    try:
        content = complete_text(config, messages, tracker=tracker, temperature=0.2)
    except Exception as exc:  # noqa: BLE001 — fallback to raw save
        print(f"[error] enrich failed: {exc}", flush=True)
        return None
    data = _extract_json(content)
    if not data:
        print("[error] enrich: не удалось разобрать JSON", flush=True)
        return None
    title = str(data.get("title") or "").strip() or _preview(text, 60)
    body = str(data.get("body") or text).strip() or text
    summary = str(data.get("summary") or "").strip()
    tags = data.get("tags") or []
    aliases = data.get("aliases") or []
    if not isinstance(tags, list):
        tags = [str(tags)]
    if not isinstance(aliases, list):
        aliases = [str(aliases)]
    return {
        "title": title,
        "body": body,
        "summary": summary,
        "tags": [str(t).strip() for t in tags if str(t).strip()],
        "aliases": [str(a).strip() for a in aliases if str(a).strip()],
    }


def expand_query(
    question: str,
    *,
    config: LlmConfig | None,
    tracker: UsageTracker | None = None,
) -> list[str]:
    if config is None:
        return []
    messages = [
        {
            "role": "system",
            "content": (
                "Для полнотекстового поиска по базе знаний верни 5–10 поисковых терминов "
                "и коротких перефраз (синонимы, аббревиатуры). "
                'Только JSON: {"terms": ["..."]}. Без пояснений.'
            ),
        },
        {"role": "user", "content": question},
    ]
    try:
        content = complete_text(config, messages, tracker=tracker, temperature=0.1)
    except Exception as exc:  # noqa: BLE001
        print(f"[error] expand failed: {exc}", flush=True)
        return []
    data = _extract_json(content)
    if not data:
        return []
    terms = data.get("terms") or []
    if not isinstance(terms, list):
        return []
    return [str(t).strip() for t in terms if str(t).strip()][:12]


def save_text(
    text: str,
    *,
    no_enrich: bool = False,
    embed: bool = True,
    conn: sqlite3.Connection | None = None,
    config: LlmConfig | None = None,
    tracker: UsageTracker | None = None,
) -> SaveResult:
    text = text.strip()
    if not text:
        raise ValueError("пустой текст заметки")

    enriched = False
    title = _preview(text, 72)
    body = text
    summary = ""
    tags: list[str] = []
    aliases: list[str] = []

    if not no_enrich:
        cfg = config if config is not None else try_load_llm_config()
        meta = enrich_note(text, config=cfg, tracker=tracker)
        if meta:
            enriched = True
            title = meta["title"]
            body = meta["body"]
            summary = meta["summary"]
            tags = meta["tags"]
            aliases = meta["aliases"]
            print(
                f"[save] enrich ok title={title!r} tags={tags} aliases={len(aliases)}",
                flush=True,
            )
        else:
            print("[save] enrich skipped → raw", flush=True)
    else:
        print("[save] --no-enrich → raw", flush=True)

    own = conn is None
    if own:
        conn = get_connection()
    assert conn is not None

    note, n_chunks, n_embedded = insert_note(
        title=title,
        body=body,
        summary=summary,
        tags=tags,
        aliases=aliases,
        embed=embed,
        conn=conn,
    )
    print(
        f"[save] id={note.id} chunks={n_chunks} embedded={n_embedded} title={note.title!r}",
        flush=True,
    )
    if own:
        conn.close()
    return SaveResult(note=note, n_chunks=n_chunks, n_embedded=n_embedded, enriched=enriched)


def search_text(
    query: str,
    *,
    conn: sqlite3.Connection | None = None,
    expand: bool = True,
    config: LlmConfig | None = None,
    tracker: UsageTracker | None = None,
    top_m: int = 40,
) -> RetrieveResult:
    own = conn is None
    if own:
        conn = get_connection()
    assert conn is not None

    terms: list[str] = []
    if expand:
        cfg = config if config is not None else try_load_llm_config()
        terms = expand_query(query, config=cfg, tracker=tracker)
        if terms:
            print(f"[expand] terms={terms}", flush=True)
        else:
            print("[expand] skip (no LLM / empty)", flush=True)

    result = retrieve(conn, query, expand_terms=terms, top_m=top_m)
    print(
        f"[retrieve] mode={result.mode} fts={result.fts_count} "
        f"dense={result.dense_count} fused={len(result.hits)} "
        f"latency={result.latency_ms:.0f}ms",
        flush=True,
    )
    if own:
        conn.close()
    return result


def ask(
    question: str,
    *,
    conn: sqlite3.Connection | None = None,
    config: LlmConfig | None = None,
    tracker: UsageTracker | None = None,
) -> AskResult:
    tracker = tracker or UsageTracker()
    cfg = config if config is not None else try_load_llm_config()
    if cfg is None:
        raise RuntimeError("Нужен DOCKHOST_AI_KEY для --ask")

    own = conn is None
    if own:
        conn = get_connection()
    assert conn is not None

    result = search_text(
        question,
        conn=conn,
        expand=True,
        config=cfg,
        tracker=tracker,
    )
    packed = pack_context(result.hits, max_cards=8, max_chunks=4)
    print(
        f"[ask] pack cards={packed.n_cards} chunks={packed.n_chunks} ~{packed.approx_chars} chars",
        flush=True,
    )

    messages = build_ask_messages(question, packed)
    t0 = time.perf_counter()
    answer = complete_text(cfg, messages, tracker=tracker, temperature=0.3)
    llm_ms = (time.perf_counter() - t0) * 1000
    print(f"[ask] llm_latency={llm_ms:.0f}ms", flush=True)

    cards = notes_from_hits(result.hits, limit=8)
    if own:
        conn.close()
    return AskResult(
        answer=answer,
        retrieve=result,
        note_cards=cards,
        pack_chars=packed.approx_chars,
        llm_ms=llm_ms,
        tracker=tracker,
    )


# Demo seed — нейтральный рабочий домен (без опоссумов)
DEMO_NOTE_1 = """
Решение по rate limiting публичного API TaskBoard.

Контекст: после пика нагрузки (маркетинговая рассылка) получили 429 от апстрима
и каскадные таймауты у клиентов мобильного приложения.

Правила:
1. Token bucket на gateway: 120 req/min на API-ключ, burst 30.
2. Для эндпоинта POST /tasks — отдельный лимит 20/min (дорогая запись).
3. При 429 клиентам отдаём Retry-After и заголовок X-RateLimit-Remaining.
4. Логируем только агрегаты (не полный body), чтобы не раздувать Loki.

Открытый вопрос: нужен ли soft-limit с предупреждением на 80% квоты в Slack.
""".strip()

DEMO_NOTE_2 = """
Кэш ответов списка проектов: Redis TTL и инвалидация.

Проблема: дашборд дергает GET /projects?org=… каждые 15 секунд; БД Postgres
на чтение упиралась в shared buffer при 200 одновременных сессиях.

Подход:
- Redis key org:{id}:projects:list, TTL 45s.
- Инвалидация при create/update/archive проекта через pub/sub канал projects:invalidate.
- Stale-while-revalidate: отдаём просроченный кэш ≤90s, параллельно обновляем.
- Метрика cache_hit_ratio в Grafana; алерт если < 0.6 за 10 минут.

Связь с лимитами: кэш снижает число запросов к API и косвенно давление на rate limit.
""".strip()

DEMO_ASK = (
    "Как снизить нагрузку на API и БД при частых опросах списка проектов, "
    "и что делать клиенту при превышении квоты запросов?"
)
