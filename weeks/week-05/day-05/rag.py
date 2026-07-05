from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from console_out import print_tagged
from history import Turn
from llm import complete
from run_log import get_run_log
from translate import OPOSSUM_TERMS

RagMode = Literal["rerank"]
CHAT_TEMPERATURE = 0.35

RAG_SYSTEM = (
    "You are a knowledgeable, friendly chat assistant about opossums.\n"
    "You answer using ONLY the Evidence excerpts below (English text).\n"
    "The Conversation block is for continuity only — never cite it as a factual source.\n"
    "Do not invent facts beyond the Evidence excerpts.\n"
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
    "- true when Evidence contains relevant facts that answer the question, including "
    "follow-ups that refer to the same topic as Conversation.\n"
    "- true when a table or list in Evidence lets you infer the answer cautiously "
    "(e.g. ranking, counts, first/second place) — cite the supporting excerpt.\n"
    "- false ONLY when Evidence is empty, wholly off-topic, or clearly lacks the "
    "specific fact asked for.\n"
    "- Do NOT set false just because rerank scores are moderate — read the excerpts.\n"
    "When context_sufficient is false:\n"
    '- answer MUST start with "Я не знаю"; briefly explain what is missing in Evidence '
    "(2-4 sentences, no invented facts).\n"
    "- clarification_hint: tell the user what to rephrase or specify.\n"
    "- sources and citations MUST be empty arrays [].\n"
    "When context_sufficient is true:\n"
    "- answer: natural, conversational Russian — like a confident expert in chat.\n"
    "- length: as much as needed — from a short reply to a detailed answer (up to ~20 "
    "sentences) when Evidence supports it.\n"
    "- you may refer briefly to earlier chat turns for continuity, but every fact must "
    "come from Evidence excerpts.\n"
    "- NEVER say you lack access to a prior answer, another study, or chat history.\n"
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
            f"Retrieval note: 0 chunks passed rerank min_score={min_score}. "
            "If Evidence is empty, set context_sufficient=false."
        )
    scores = [float(h.get("rerank_score", 0)) for h in hits]
    top = max(scores)
    return (
        f"Retrieval note: {len(hits)} Evidence chunk(s); top rerank_score={top:.3f}. "
        "Judge sufficiency from excerpt content, not score alone."
    )


def _format_conversation(history: list[Turn], *, max_turns: int = 10) -> str:
    if not history:
        return "(no prior conversation)"
    lines: list[str] = []
    for turn in history[-max_turns:]:
        if turn.role not in {"user", "assistant"} or not turn.content.strip():
            continue
        label = "User" if turn.role == "user" else "Assistant"
        lines.append(f"{label}: {turn.content}")
    return "\n".join(lines) if lines else "(no prior conversation)"


def _build_user_message(
    *,
    hint: str,
    conversation: str,
    evidence: str,
    question_en: str,
) -> str:
    return (
        f"{hint}\n\n"
        "=== Conversation (continuity only, NOT a factual source) ===\n"
        f"{conversation}\n\n"
        "=== Evidence (ONLY source of facts; cite these) ===\n"
        f"{evidence}\n\n"
        "=== Question ===\n"
        f"{question_en}"
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
    sources = _parse_sources(data.get("sources"))
    citations = _parse_citations(data.get("citations"))
    if sufficient and not sources:
        sufficient = False
    hint = str(data.get("clarification_hint", "")).strip()
    if sufficient:
        hint = ""
    return RagResponse(
        answer=str(data.get("answer", "")).strip(),
        context_sufficient=sufficient,
        clarification_hint=hint,
        sources=sources,
        citations=citations,
    )


def generate_with_rag(
    question_en: str,
    hits: list[dict[str, Any]],
    *,
    history: list[Turn] | None = None,
    min_score: float = 0.15,
) -> RagResponse:
    evidence = _format_context(hits)
    hint = _build_retrieval_hint(hits, min_score=min_score)
    conversation = _format_conversation(history or [], max_turns=10)
    user_content = _build_user_message(
        hint=hint,
        conversation=conversation,
        evidence=evidence,
        question_en=question_en,
    )
    log = get_run_log()
    log.block("rag_retrieval_hint", hint)
    log.block("rag_conversation", conversation, max_chars=4000)
    log.hits("rag_context_chunks", hits, limit=10)
    for index, hit in enumerate(hits[:4], start=1):
        text = str(hit.get("text", ""))
        log.block(f"rag_chunk_{index}_text", text, max_chars=1200)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": RAG_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    log.kv("rag_history_turns", len(history or []))
    raw = complete(
        messages,
        temperature=CHAT_TEMPERATURE,
        stage="rag",
        log_message_chars=25000,
        log_response_chars=5000,
    )
    try:
        response = _parse_response(raw)
    except (ValueError, json.JSONDecodeError):
        print_tagged("retry", "RAG JSON parse failed, retrying once")
        log.line("RAG JSON parse failed, retrying once", indent=1)
        retry_messages = messages + [
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": "Return ONLY valid JSON matching the schema. No markdown.",
            },
        ]
        raw = complete(
            retry_messages,
            temperature=0,
            stage="rag_retry",
            log_message_chars=25000,
            log_response_chars=5000,
        )
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
