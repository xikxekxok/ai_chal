"""Verification: sources, citations, groundedness."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from console_out import print_section
from llm import complete
from rag import RagResponse

GROUNDED_SYSTEM = (
    "You check whether a Russian answer is grounded in the provided English citations.\n"
    "The answer must not contain factual claims that are absent from the citations.\n"
    "Ignore style, phrasing, and EN→RU translation differences.\n"
    "If context_sufficient is false, grounded is true when the answer only says "
    "it cannot answer and explains what is missing (no invented facts).\n"
    'Return ONLY valid JSON: {"grounded": true/false, "reason": "brief note"}'
)

DONT_KNOW_MARKERS = ("не знаю", "нет ответа", "недостаточно", "не содержит", "не могу ответить")


@dataclass
class VerifyResult:
    context_sufficient: bool
    has_clarification: bool
    has_sources: bool
    has_citations: bool
    valid_chunk_ids: bool
    quotes_in_chunks: bool
    grounded: bool
    reason: str = ""
    failures: list[str] = field(default_factory=list)


def _normalize(text: str) -> str:
    return " ".join(text.split()).lower()


def _chunk_map(rag_hits: list[dict[str, Any]]) -> dict[str, str]:
    return {str(h.get("chunk_id", "")): h.get("text") or "" for h in rag_hits}


def _quote_in_chunk(quote: str, chunk_text: str) -> bool:
    if not quote.strip():
        return False
    norm_quote = _normalize(quote)
    norm_chunk = _normalize(chunk_text)
    if norm_quote in norm_chunk:
        return True
    prefix = norm_quote[:80]
    return len(prefix) >= 40 and prefix in norm_chunk


def check_structural(
    response: RagResponse,
    rag_hits: list[dict[str, Any]],
) -> tuple[bool, bool, bool, bool, bool, list[str]]:
    failures: list[str] = []

    if not response.context_sufficient:
        if response.sources:
            failures.append("sources must be empty when context insufficient")
        if response.citations:
            failures.append("citations must be empty when context insufficient")
        answer_lower = response.answer.lower()
        if not any(marker in answer_lower for marker in DONT_KNOW_MARKERS):
            failures.append("answer should say 'не знаю' when context insufficient")
        has_clarification = bool(response.clarification_hint.strip())
        if not has_clarification:
            failures.append("clarification_hint required when context insufficient")
        has_sources = len(response.sources) == 0
        has_citations = len(response.citations) == 0
        return has_clarification, has_sources, has_citations, True, True, failures

    has_clarification = not bool(response.clarification_hint.strip())
    if response.clarification_hint.strip():
        failures.append("clarification_hint should be empty when context sufficient")

    has_sources = len(response.sources) >= 1
    if not has_sources:
        failures.append("no sources")

    has_citations = len(response.citations) >= 1
    if not has_citations:
        failures.append("no citations")

    valid_ids = {str(h.get("chunk_id", "")) for h in rag_hits}
    chunks = _chunk_map(rag_hits)

    valid_chunk_ids = True
    for src in response.sources:
        if src.chunk_id not in valid_ids:
            valid_chunk_ids = False
            failures.append(f"unknown source chunk_id={src.chunk_id}")

    quotes_ok = True
    for cite in response.citations:
        if cite.chunk_id not in valid_ids:
            quotes_ok = False
            failures.append(f"unknown citation chunk_id={cite.chunk_id}")
            continue
        if not _quote_in_chunk(cite.quote, chunks.get(cite.chunk_id, "")):
            quotes_ok = False
            failures.append(f"quote not in chunk {cite.chunk_id}")

    return has_clarification, has_sources, has_citations, valid_chunk_ids, quotes_ok, failures


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
    raise ValueError(f"Cannot parse verify JSON: {text[:200]}")


def check_grounded(
    question_ru: str,
    response: RagResponse,
) -> tuple[bool, str]:
    if not response.context_sufficient:
        answer_lower = response.answer.lower()
        ok = any(marker in answer_lower for marker in DONT_KNOW_MARKERS)
        return ok, "insufficient context" + (" (hedged)" if ok else "")

    if not response.citations:
        answer_lower = response.answer.lower()
        hedged = any(marker in answer_lower for marker in DONT_KNOW_MARKERS)
        return hedged, "no citations" + (" (hedged answer)" if hedged else "")

    cites_text = "\n\n".join(f"[{c.chunk_id}] {c.quote}" for c in response.citations)
    result = complete(
        [
            {"role": "system", "content": GROUNDED_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"context_sufficient: {response.context_sufficient}\n"
                    f"Question (Russian): {question_ru}\n\n"
                    f"Answer (Russian):\n{response.answer}\n\n"
                    f"Citations (English):\n{cites_text}"
                ),
            },
        ],
        temperature=0,
    )
    parsed = _extract_json(result)
    grounded = bool(parsed.get("grounded"))
    reason = str(parsed.get("reason", ""))
    return grounded, reason


def verify_response(
    question_ru: str,
    response: RagResponse,
    rag_hits: list[dict[str, Any]],
) -> VerifyResult:
    has_clarification, has_sources, has_citations, valid_chunk_ids, quotes_ok, failures = (
        check_structural(response, rag_hits)
    )
    grounded, reason = check_grounded(question_ru, response)
    if not grounded:
        failures.append(f"not grounded: {reason}")

    return VerifyResult(
        context_sufficient=response.context_sufficient,
        has_clarification=has_clarification,
        has_sources=has_sources,
        has_citations=has_citations,
        valid_chunk_ids=valid_chunk_ids,
        quotes_in_chunks=quotes_ok,
        grounded=grounded,
        reason=reason,
        failures=failures,
    )


def format_verify(result: VerifyResult) -> str:
    ctx = "ok" if result.context_sufficient else "insufficient"
    clar = "ok" if result.has_clarification else "FAIL"
    checks = [
        f"context: {ctx}",
        f"clarification: {clar}",
        f"sources: {'ok' if result.has_sources else 'FAIL'}",
        f"citations: {'ok' if result.has_citations else 'FAIL'}",
        f"chunk_ids: {'ok' if result.valid_chunk_ids else 'FAIL'}",
        f"quotes: {'ok' if result.quotes_in_chunks else 'FAIL'}",
        f"grounded: {'ok' if result.grounded else 'FAIL'}",
    ]
    lines = [" · ".join(checks)]
    if result.reason:
        lines.append(f"reason: {result.reason}")
    if result.failures:
        lines.append("failures: " + "; ".join(result.failures))
    return "\n".join(lines)


@dataclass
class VerifyTotals:
    total: int = 0
    context_ok: int = 0
    sources_ok: int = 0
    citations_ok: int = 0
    grounded_ok: int = 0
    wide_total: int = 0
    wide_sufficient: int = 0


def print_verify_total(totals: VerifyTotals) -> None:
    n = totals.total
    lines = [
        f"context_sufficient (rerank): {totals.context_ok}/{n}",
        f"sources: {totals.sources_ok}/{n}",
        f"citations: {totals.citations_ok}/{n}",
        f"grounded: {totals.grounded_ok}/{n}",
    ]
    if totals.wide_total:
        lines.append(f"wide fallback sufficient: {totals.wide_sufficient}/{totals.wide_total}")
    print_section("verify-total", "\n".join(lines), layout="block")
