from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from console_out import print_tagged
from profiles import RAGProfile
from rag_cite import RagResponse, answer_insufficient, generate_cite_rag
from rerank import rerank_filter
from retrieve import retrieve


@dataclass
class PipelineResult:
    question_ru: str
    question_en: str
    profile: RAGProfile
    retrieve_hits: list[dict[str, Any]] = field(default_factory=list)
    rag_hits: list[dict[str, Any]] = field(default_factory=list)
    dropped: list[dict[str, Any]] = field(default_factory=list)
    response: RagResponse | None = None
    response_wide: RagResponse | None = None


def _needs_wide_fallback(response: RagResponse | None, rag_hits: list[dict[str, Any]]) -> bool:
    if not rag_hits:
        return True
    if response is None:
        return True
    return answer_insufficient(response.answer)


def run_cite_pipeline(
    question_ru: str,
    question_en: str,
    chunks: list[dict[str, Any]],
    profile: RAGProfile,
    *,
    generate_answer: bool = True,
) -> PipelineResult:
    config = profile.pipeline
    hits = retrieve(question_en, chunks, top_k=config.retrieve_k)
    print_tagged("retrieve", f"top-{len(hits)} cosine")

    rag_hits, dropped = rerank_filter(
        question_en,
        hits,
        min_score=config.min_score,
        top_k=config.rag_k,
    )
    kept_scores = [f"{h.get('rerank_score', 0):.3f}" for h in rag_hits[:3]]
    print_tagged(
        "rerank",
        f"kept={len(rag_hits)} dropped={len(dropped)} "
        f"min_score={config.min_score} top_scores=[{', '.join(kept_scores)}]",
    )

    response: RagResponse | None = None
    response_wide: RagResponse | None = None
    if generate_answer:
        response = generate_cite_rag(question_en, rag_hits, profile, mode="rerank")
        if _needs_wide_fallback(response, rag_hits) and hits:
            response_wide = generate_cite_rag(question_en, hits, profile, mode="wide")

    return PipelineResult(
        question_ru=question_ru,
        question_en=question_en,
        profile=profile,
        retrieve_hits=hits,
        rag_hits=rag_hits,
        dropped=dropped,
        response=response,
        response_wide=response_wide,
    )
