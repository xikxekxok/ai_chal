"""Сборка RAG-контекста для ассистента."""

from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = """\
Ты ассистент разработчика по учебному проекту TaskBoard.
Отвечай по-русски, кратко и по делу.
Опирайся на документацию из контекста и на результаты MCP-tools (git, файлы).
Не выдумывай эндпоинты и поля, которых нет в документации.
Если данных недостаточно — скажи об этом прямо.
Когда полезно для ответа про окружение — вызови git_branch или list_files.
"""


def format_context(hits: list[dict[str, Any]]) -> str:
    if not hits:
        return "(документация не найдена)"
    parts: list[str] = []
    for hit in hits:
        path = hit.get("path") or "?"
        score = hit.get("score", 0.0)
        text = hit.get("text") or ""
        parts.append(f"### {path} (score={score:.3f})\n{text}")
    return "\n\n".join(parts)


def build_user_message(question: str, hits: list[dict[str, Any]]) -> str:
    context = format_context(hits)
    return (
        f"Документация проекта (RAG):\n---\n{context}\n---\n\n"
        f"Вопрос: {question}"
    )
