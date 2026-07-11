from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from console_out import (
    begin_stream_section,
    end_stream_section,
    print_tagged,
    write_stream_delta,
)
from llm import load_ollama_config, stream_local
from profiles import RAGProfile
from translate import OPOSSUM_TERMS

RagMode = Literal["rerank", "wide"]

RAG_SYSTEM = (
    "You answer the user's question in Russian using ONLY the reference excerpts "
    "below (English text).\n"
    "Do not invent facts beyond the excerpts.\n"
    "Write a direct, natural answer.\n"
    "Requirements:\n"
    "- Name the books/sources you rely on (title, source_id from the excerpt headers).\n"
    "- Include short verbatim English quotes from the excerpts (1–3 sentences each) "
    "to support key facts.\n"
    "- Mention chunk_id when citing a quote, e.g. «…» [chunk_id=…].\n"
    "If the excerpts do not contain enough to answer, start with «Я не знаю» and briefly "
    "explain what is missing — do not guess.\n"
    f"{OPOSSUM_TERMS}"
)


@dataclass
class RagResponse:
    answer: str
    hits: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: int = 0
    usage: dict[str, Any] = field(default_factory=dict)
    thinking: str = ""


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _format_context(
    chunks: list[dict[str, Any]],
    *,
    mode: RagMode,
    max_chunk_chars: int,
) -> str:
    if not chunks:
        return "(no reference material retrieved)"
    parts: list[str] = []
    for chunk in chunks:
        text = _truncate_text(chunk.get("text") or "", max_chunk_chars)
        chunk_id = chunk.get("chunk_id", "")
        source_id = chunk.get("source_id", "")
        if mode == "rerank" and chunk.get("rerank_score") is not None:
            score_note = f" rerank_score={chunk['rerank_score']:.3f}"
        elif mode == "wide" and chunk.get("score") is not None:
            score_note = f" cosine_score={chunk['score']:.4f}"
        else:
            score_note = ""
        parts.append(
            f"--- chunk_id={chunk_id} source_id={source_id}{score_note} ---\n"
            f"Book: {chunk.get('title')}\n"
            f"Section: {chunk.get('section')}\n"
            f"{text}"
        )
    return "\n\n".join(parts)


def _build_retrieval_hint(
    hits: list[dict[str, Any]],
    *,
    mode: RagMode,
    min_score: float,
) -> str:
    if mode == "wide":
        if not hits:
            return "Retrieval: 0 cosine chunks — excerpts are empty."
        scores = [float(h.get("score", 0)) for h in hits]
        top = max(scores)
        return (
            f"Retrieval: {len(hits)} cosine chunk(s), no rerank filter; "
            f"top cosine_score={top:.4f}."
        )
    if not hits:
        return (
            f"Retrieval: 0 chunks above min_score={min_score}. "
            "Context is weak — say «Я не знаю» unless excerpts clearly answer."
        )
    scores = [float(h.get("rerank_score", 0)) for h in hits]
    top = max(scores)
    strength = "strong" if top >= 0.35 else "moderate" if top >= min_score else "weak"
    return (
        f"Retrieval: {len(hits)} chunk(s) above min_score={min_score}; "
        f"top rerank_score={top:.3f} ({strength})."
    )


def generate_cite_rag(
    question_en: str,
    hits: list[dict[str, Any]],
    profile: RAGProfile,
    *,
    mode: RagMode = "rerank",
) -> RagResponse:
    min_score = profile.pipeline.min_score
    context = _format_context(hits, mode=mode, max_chunk_chars=profile.max_chunk_chars)
    hint = _build_retrieval_hint(hits, mode=mode, min_score=min_score)
    messages = [
        {"role": "system", "content": RAG_SYSTEM},
        {
            "role": "user",
            "content": (
                f"{hint}\n\nReference material:\n{context}\n\n"
                f"Question: {question_en}\n\nAnswer in Russian."
            ),
        },
    ]
    cfg = load_ollama_config(model=profile.model)
    content_tag = f"rag-{mode}"

    def on_thinking(delta: str) -> None:
        begin_stream_section("thinking")
        write_stream_delta(delta, tag="thinking")

    def on_content(delta: str) -> None:
        begin_stream_section(content_tag)
        write_stream_delta(delta, tag=content_tag)

    result = stream_local(
        messages,
        config=cfg,
        gen=profile.gen,
        on_thinking=on_thinking,
        on_content=on_content,
    )
    end_stream_section()
    print_tagged("local", f"cite answer ({result.latency_ms} ms)")
    return RagResponse(
        answer=result.content.strip(),
        hits=hits,
        latency_ms=result.latency_ms,
        usage=result.usage,
        thinking=result.thinking,
    )


def format_rag_summary(response: RagResponse) -> str:
    return f"{len(response.hits)} chunks · {response.latency_ms} ms"


def format_chunks_used(hits: list[dict[str, Any]]) -> str:
    if not hits:
        return "(none)"
    lines: list[str] = []
    for chunk in hits:
        lines.append(
            f"  {chunk.get('source_id', '')} · {chunk.get('title', '')!r} · "
            f"section={chunk.get('section', '')!r} · chunk_id={chunk.get('chunk_id', '')}"
        )
    return "\n".join(lines)


def answer_insufficient(answer: str) -> bool:
    normalized = answer.strip().casefold()
    return normalized.startswith("я не знаю") or normalized.startswith("i don't know")
