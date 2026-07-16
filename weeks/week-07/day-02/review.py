from __future__ import annotations

from typing import Any

from llm import complete
from rag import Chunk

SYSTEM_PROMPT = """Ты опытный reviewer pull request.
Смотри только на существенные проблемы: баги, регрессии, архитектурные риски,
безопасность, поддерживаемость. Не придумывай проблемы, если сигнал слабый.

Верни ответ строго на русском языке и строго в таком формате:
## Потенциальные баги
- ...

## Архитектурные проблемы
- ...

## Рекомендации
- ...

Если в секции нечего сказать, напиши "- Ничего критичного не нашёл."
Пиши кратко и по делу.
"""


def build_review_prompt(
    pull_request: dict[str, Any],
    files: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    comments: list[dict[str, Any]],
    context_chunks: list[Chunk],
) -> str:
    def format_feedback(kind: str, item: dict[str, Any]) -> str:
        login = item.get("user", {}).get("login", "unknown")
        body = item.get("body") or "<empty>"
        return f"- {kind} by {login}: {body}"

    file_summaries = []
    for file in files:
        patch_preview = (file.get("patch") or "").strip()
        if len(patch_preview) > 1200:
            patch_preview = f"{patch_preview[:1200]}\n...<truncated>"
        file_summaries.append(
            "\n".join(
                [
                    f"- path: {file['filename']}",
                    f"  status: {file.get('status')}",
                    f"  additions: {file.get('additions')}, deletions: {file.get('deletions')}",
                    f"  patch:\n{patch_preview or '  <patch unavailable>'}",
                ]
            )
        )

    prior_feedback = [format_feedback("review", item) for item in reviews if item.get("body")]
    prior_feedback.extend(
        format_feedback("comment", item)
        for item in comments
        if item.get("body")
    )

    rag_context = []
    for chunk in context_chunks:
        rag_context.append(f"[{chunk.path}]\n{chunk.text}")

    title = pull_request.get("title", "")
    body = pull_request.get("body") or ""
    return f"""
PR: #{pull_request["number"]} {title}
Автор: {pull_request.get("user", {}).get("login", "unknown")}
Ветка: {pull_request.get("head", {}).get("ref")} -> {pull_request.get("base", {}).get("ref")}
Описание:
{body or "<empty>"}

Изменённые файлы:
{chr(10).join(file_summaries) or "<no files>"}

Предыдущее обсуждение:
{chr(10).join(prior_feedback) or "<none>"}

Контекст репозитория:
{chr(10).join(rag_context) or "<no context>"}
""".strip()


def review_pull_request(
    pull_request: dict[str, Any],
    files: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    comments: list[dict[str, Any]],
    context_chunks: list[Chunk],
) -> str:
    prompt = build_review_prompt(
        pull_request=pull_request,
        files=files,
        reviews=reviews,
        comments=comments,
        context_chunks=context_chunks,
    )
    return complete(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
    )
