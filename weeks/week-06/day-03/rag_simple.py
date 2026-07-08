from __future__ import annotations

from typing import Any

from console_out import print_tagged
from llm import complete_local
from translate import OPOSSUM_TERMS

RAG_INSTRUCTIONS = (
    "You answer the user's question in Russian.\n"
    "Use ONLY the reference material below (English text). Do not invent facts.\n"
    "Write a direct, natural answer — as if you simply know the topic.\n"
    "Do NOT expose retrieval: no «согласно источнику», «в отрывке», «в другом фрагменте», "
    "«предоставленные выдержки», chunk numbers, bracket citations like [1] or [7: …].\n"
    "Weave book facts into normal speech when helpful "
    "(e.g. «В сказке Бёрджесса Дедушка Лягушка рассказывает…»).\n"
    "If the material does not contain enough to answer, say so briefly in plain Russian "
    "without mentioning documents or excerpts.\n"
    f"{OPOSSUM_TERMS}"
)


def _format_context(chunks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for chunk in chunks:
        text = chunk.get("text") or ""
        parts.append(
            f"Book: {chunk.get('title')}\n"
            f"Section: {chunk.get('section')}\n"
            f"{text}"
        )
    return "\n---\n".join(parts)


def generate_simple_rag(
    question_en: str,
    hits: list[dict[str, Any]],
) -> tuple[str, int]:
    context = _format_context(hits)
    messages = [
        {"role": "system", "content": RAG_INSTRUCTIONS},
        {
            "role": "user",
            "content": (
                f"Reference material:\n---\n{context}\n---\n\n"
                f"Question: {question_en}\n\nAnswer in Russian only."
            ),
        },
    ]
    result = complete_local(messages)
    print_tagged("local", f"simple answer ({result.latency_ms} ms)")
    return result.content.strip(), result.latency_ms
