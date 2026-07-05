from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from console_out import print_tagged
from history import Turn
from llm import complete

QUERY_SYSTEM = (
    "You prepare search queries for a semantic-search retrieval system about opossums.\n"
    "Given chat history (if any) and the user's current Russian message, output ONLY "
    "valid JSON — no markdown fences, no extra text.\n"
    "Schema:\n"
    "{\n"
    '  "standalone_query_en": "self-contained English search query",\n'
    '  "is_follow_up": true\n'
    "}\n"
    "Rules for standalone_query_en:\n"
    "- One clear English question or phrase suitable for embedding-based search.\n"
    "- Must be fully self-contained: include entities, topics, and constraints from "
    "earlier turns when the current message uses pronouns or vague references "
    "(e.g. «из них», «подробнее», «а что насчёт»).\n"
    "- Do NOT answer the question. Do NOT invent facts beyond what history + current "
    "message imply.\n"
    "- Opossum/possum in English, never raccoon.\n"
    "Rules for is_follow_up:\n"
    "- true when the current message depends on prior chat turns to be understood.\n"
    "- false for a standalone new question with no reliance on history."
)


@dataclass
class QueryResult:
    standalone_query_en: str
    is_follow_up: bool


def _format_history_block(history: list[Turn]) -> str:
    if not history:
        return "Chat history: (none — standalone message)"
    lines: list[str] = []
    for turn in history:
        label = "User" if turn.role == "user" else "Assistant"
        lines.append(f"{label}: {turn.content}")
    return "Chat history:\n" + "\n".join(lines)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        data = json.loads(match.group())
        if isinstance(data, dict):
            return data
    raise ValueError(f"Cannot parse query JSON: {text[:200]}")


def _parse_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    if value is None:
        return default
    return bool(value)


def _parse_query_response(raw: str, *, history: list[Turn]) -> QueryResult:
    data = _extract_json(raw)
    standalone = str(data.get("standalone_query_en", "")).strip()
    if not standalone:
        raise ValueError("standalone_query_en is empty")
    is_follow_up = _parse_bool(data.get("is_follow_up"), default=bool(history))
    return QueryResult(standalone_query_en=standalone, is_follow_up=is_follow_up)


def process_query(text_ru: str, *, history: list[Turn] | None = None) -> QueryResult:
    turns = history or []
    history_block = _format_history_block(turns)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": QUERY_SYSTEM},
        {
            "role": "user",
            "content": (
                f"{history_block}\n\n"
                f"Current Russian message (build search query only, do not answer):\n"
                f"{text_ru}"
            ),
        },
    ]
    raw = complete(messages, temperature=0)
    try:
        result = _parse_query_response(raw, history=turns)
    except (ValueError, json.JSONDecodeError):
        print_tagged("retry", "query JSON parse failed, retrying once")
        retry_messages = messages + [
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": "Return ONLY valid JSON matching the schema. No markdown.",
            },
        ]
        raw = complete(retry_messages, temperature=0)
        result = _parse_query_response(raw, history=turns)

    follow_up = "true" if result.is_follow_up else "false"
    print_tagged(
        "query",
        f"standalone={result.standalone_query_en} follow_up={follow_up}",
    )
    return result
