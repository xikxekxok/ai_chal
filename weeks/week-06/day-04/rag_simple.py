from __future__ import annotations

from typing import Any

from console_out import (
    begin_stream_section,
    end_stream_section,
    print_tagged,
    write_stream_delta,
)
from llm import load_ollama_config, stream_local
from profiles import RAGProfile
from translate import OPOSSUM_TERMS

RAG_INSTRUCTIONS = (
    "Answer in Russian using ONLY the excerpts below. Natural speech, no citation markers.\n"
    "If excerpts lack the answer, say so briefly in Russian.\n"
    f"{OPOSSUM_TERMS}"
)


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _format_context(chunks: list[dict[str, Any]], max_chunk_chars: int) -> str:
    parts: list[str] = []
    for chunk in chunks:
        text = _truncate_text(chunk.get("text") or "", max_chunk_chars)
        parts.append(
            f"Book: {chunk.get('title')}\n"
            f"Section: {chunk.get('section')}\n"
            f"{text}"
        )
    return "\n---\n".join(parts)


def generate_simple_rag(
    question_en: str,
    hits: list[dict[str, Any]],
    profile: RAGProfile,
) -> tuple[str, int]:
    context = _format_context(hits, profile.max_chunk_chars)
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
    cfg = load_ollama_config(model=profile.model)

    def on_thinking(delta: str) -> None:
        begin_stream_section("thinking")
        write_stream_delta(delta, tag="thinking")

    def on_content(delta: str) -> None:
        begin_stream_section("answer-rag")
        write_stream_delta(delta, tag="answer-rag")

    result = stream_local(
        messages,
        config=cfg,
        gen=profile.gen,
        on_thinking=on_thinking,
        on_content=on_content,
    )
    end_stream_section()
    print_tagged("local", f"simple answer ({result.latency_ms} ms)")
    return result.content.strip(), result.latency_ms
