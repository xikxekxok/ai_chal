from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from console_out import print_tagged
from history import Turn, history_for_llm
from llm import complete
from translate import OPOSSUM_TERMS

RagMode = Literal["rerank"]
CHAT_TEMPERATURE = 0.35

RAG_SYSTEM = (
    "You are a knowledgeable, friendly chat assistant about opossums.\n"
    "You answer using ONLY the reference material below (English text).\n"
    "Do not invent facts beyond the excerpts.\n"
    "Return ONLY valid JSON — no markdown fences, no extra text.\n"
    "Schema:\n"
    "{\n"
    '  "context_sufficient": true,\n'
    '  "answer": "answer in Russian",\n'
    '  "clarification_hint": "what to clarify (RU, 1-2 sentences; empty if sufficient)",\n'
    '  "sources": [\n'
    '    {"source_id": "…", "title": "…", "section": "…", "chunk_id": "…"}\n'
    "  ],\n"
    '  "citations": [\n'
    '    {"chunk_id": "…", "quote": "verbatim excerpt copied from that chunk"}\n'
    "  ]\n"
    "}\n"
    "Rules for context_sufficient:\n"
    "- true ONLY when the excerpts contain enough facts to answer the question directly.\n"
    "- false when: no material, material is off-topic, or excerpts mention the topic "
    "but do NOT contain the actual answer.\n"
    "- false when retrieval hint says context is weak and excerpts do not clearly answer.\n"
    "When context_sufficient is false:\n"
    '- answer MUST start with "Я не знаю"; briefly explain what is missing in the excerpts '
    "(2-4 sentences, no invented facts).\n"
    "- clarification_hint: tell the user what to rephrase or specify.\n"
    "- sources and citations MUST be empty arrays [].\n"
    "When context_sufficient is true:\n"
    "- answer: natural, conversational Russian — like a confident expert in chat.\n"
    "- length: as much as needed — from a short reply to a detailed answer (up to ~20 "
    "sentences) when the excerpts support it.\n"
    "- you may refer briefly to earlier chat turns when relevant, but facts only from excerpts.\n"
    "- clarification_hint: empty string.\n"
    "- sources: one entry per chunk you rely on.\n"
    "- citations: verbatim English quotes (short, 1–3 sentences).\n"
    f"{OPOSSUM_TERMS}"
)


@dataclass
class SourceRef:
    source_id: str
    title: str
    section: str
    chunk_id: str


@dataclass
class Citation:
    chunk_id: str
    quote: str


@dataclass
class RagResponse:
    answer: str
    context_sufficient: bool
    clarification_hint: str = ""
    sources: list[SourceRef] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)


def _format_context(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return "(no reference material retrieved)"
    parts: list[str] = []
    for chunk in chunks:
        text = chunk.get("text") or ""
        chunk_id = chunk.get("chunk_id", "")
        source_id = chunk.get("source_id", "")
        score_note = ""
        if chunk.get("rerank_score") is not None:
            score_note = f" rerank_score={chunk['rerank_score']:.3f}"
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
    min_score: float,
) -> str:
    if not hits:
        return (
            f"Retrieval: 0 chunks above min_score={min_score}. "
            "Context is weak — set context_sufficient=false unless excerpts clearly answer."
        )
    scores = [float(h.get("rerank_score", 0)) for h in hits]
    top = max(scores)
    strength = "strong" if top >= 0.35 else "moderate" if top >= min_score else "weak"
    return (
        f"Retrieval: {len(hits)} chunk(s) above min_score={min_score}; "
        f"top rerank_score={top:.3f} ({strength}). "
        "If excerpts do not directly answer the question, set context_sufficient=false."
    )


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
    raise ValueError(f"Cannot parse RAG JSON: {text[:200]}")


def _parse_bool(value: Any, *, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    if value is None:
        return default
    return bool(value)


def _parse_sources(raw: Any) -> list[SourceRef]:
    if not isinstance(raw, list):
        return []
    sources: list[SourceRef] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        sources.append(
            SourceRef(
                source_id=str(item.get("source_id", "")),
                title=str(item.get("title", "")),
                section=str(item.get("section", "")),
                chunk_id=str(item.get("chunk_id", "")),
            )
        )
    return sources


def _parse_citations(raw: Any) -> list[Citation]:
    if not isinstance(raw, list):
        return []
    citations: list[Citation] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        citations.append(
            Citation(
                chunk_id=str(item.get("chunk_id", "")),
                quote=str(item.get("quote", "")),
            )
        )
    return citations


def _parse_response(raw: str) -> RagResponse:
    data = _extract_json(raw)
    sufficient = _parse_bool(data.get("context_sufficient"), default=True)
    hint = str(data.get("clarification_hint", "")).strip()
    if sufficient:
        hint = ""
    return RagResponse(
        answer=str(data.get("answer", "")).strip(),
        context_sufficient=sufficient,
        clarification_hint=hint,
        sources=_parse_sources(data.get("sources")),
        citations=_parse_citations(data.get("citations")),
    )


def generate_with_rag(
    question_en: str,
    hits: list[dict[str, Any]],
    *,
    history: list[Turn] | None = None,
    min_score: float = 0.15,
) -> RagResponse:
    context = _format_context(hits)
    hint = _build_retrieval_hint(hits, min_score=min_score)
    messages: list[dict[str, str]] = [{"role": "system", "content": RAG_SYSTEM}]
    messages.extend(history_for_llm(history or [], max_turns=10))
    messages.append(
        {
            "role": "user",
            "content": (f"{hint}\n\nReference material:\n{context}\n\nQuestion: {question_en}"),
        }
    )
    raw = complete(messages, temperature=CHAT_TEMPERATURE)
    try:
        response = _parse_response(raw)
    except (ValueError, json.JSONDecodeError):
        print_tagged("retry", "RAG JSON parse failed, retrying once")
        retry_messages = messages + [
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": "Return ONLY valid JSON matching the schema. No markdown.",
            },
        ]
        raw = complete(retry_messages, temperature=0)
        response = _parse_response(raw)

    return response


def format_rag_summary(response: RagResponse) -> str:
    flag = "sufficient" if response.context_sufficient else "insufficient"
    return (
        f"context={flag} · {len(response.sources)} sources · "
        f"{len(response.citations)} citations"
    )


def format_sources(sources: list[SourceRef]) -> str:
    if not sources:
        return "(none)"
    lines: list[str] = []
    for src in sources:
        lines.append(
            f"  {src.source_id} · {src.title!r} · section={src.section!r} · chunk_id={src.chunk_id}"
        )
    return "\n".join(lines)


def format_citations(citations: list[Citation]) -> str:
    if not citations:
        return "(none)"
    lines: list[str] = []
    for cite in citations:
        quote = cite.quote.replace("\n", " ")
        lines.append(f"  [{cite.chunk_id}] {quote!r}")
    return "\n".join(lines)
