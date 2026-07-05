from __future__ import annotations

from typing import Any

from llm import complete
from retrieve import retrieve
from translate import OPOSSUM_TERMS, translate_to_en

CONTEXT_PREVIEW = 600

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
        preview = text[:CONTEXT_PREVIEW]
        if len(text) > CONTEXT_PREVIEW:
            preview += "…"
        parts.append(
            f"Book: {chunk.get('title')}\n"
            f"Section: {chunk.get('section')}\n"
            f"{preview}"
        )
    return "\n---\n".join(parts)


def _build_rag_messages(
    question_en: str, chunks: list[dict[str, Any]]
) -> list[dict[str, str]]:
    context = _format_context(chunks)
    return [
        {"role": "system", "content": RAG_INSTRUCTIONS},
        {
            "role": "user",
            "content": f"Reference material:\n---\n{context}\n---\n\nQuestion: {question_en}",
        },
    ]


def _build_direct_prompt(question_ru: str) -> str:
    return (
        "Answer the question in Russian, directly and naturally.\n"
        f"{OPOSSUM_TERMS}\n"
        f"Question: {question_ru}"
    )


def generate_with_rag(
    question_en: str,
    hits: list[dict[str, Any]],
) -> str:
    return complete(_build_rag_messages(question_en, hits)).strip()


def generate_without_rag(question_ru: str) -> str:
    return complete(
        [{"role": "user", "content": _build_direct_prompt(question_ru)}]
    ).strip()


def ask_with_rag(
    question_ru: str,
    chunks: list[dict[str, Any]],
    *,
    top_k: int = 10,
    question_en: str | None = None,
    hits: list[dict[str, Any]] | None = None,
) -> str:
    if question_en is None:
        question_en = translate_to_en(question_ru)
    if hits is None:
        hits = retrieve(question_en, chunks, top_k=top_k)
    return generate_with_rag(question_en, hits)


def ask_without_rag(question_ru: str) -> str:
    return generate_without_rag(question_ru)
