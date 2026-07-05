from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from console_out import print_tagged
from rag import RagResponse, generate_with_rag
from rerank import rerank_filter
from retrieve import retrieve
from translate import translate_to_en


@dataclass
class PipelineConfig:
    retrieve_k: int = 20
    rag_k: int = 4
    min_score: float = 0.15


@dataclass
class PipelineResult:
    question_ru: str
    question_en: str
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
    return not response.context_sufficient


def run_pipeline(
    question_ru: str,
    chunks: list[dict[str, Any]],
    config: PipelineConfig,
    *,
    generate_answer: bool = True,
    question_en: str | None = None,
) -> PipelineResult:
    if question_en is None:
        question_en = translate_to_en(question_ru)

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
        response = generate_with_rag(
            question_en,
            rag_hits,
            mode="rerank",
            min_score=config.min_score,
        )
        if _needs_wide_fallback(response, rag_hits) and hits:
            response_wide = generate_with_rag(
                question_en,
                hits,
                mode="wide",
                min_score=config.min_score,
            )

    return PipelineResult(
        question_ru=question_ru,
        question_en=question_en,
        retrieve_hits=hits,
        rag_hits=rag_hits,
        dropped=dropped,
        response=response,
        response_wide=response_wide,
    )
