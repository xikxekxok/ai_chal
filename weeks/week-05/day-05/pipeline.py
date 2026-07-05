from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from console_out import print_tagged
from history import Turn
from query import process_query
from rag import RagResponse, generate_with_rag
from rerank import rerank_filter
from retrieve import retrieve


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


def run_pipeline(
    question_ru: str,
    chunks: list[dict[str, Any]],
    config: PipelineConfig,
    *,
    history: list[Turn] | None = None,
    generate_answer: bool = True,
) -> PipelineResult:
    query_result = process_query(question_ru, history=history or [])
    question_en = query_result.standalone_query_en

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
    if generate_answer:
        response = generate_with_rag(
            question_en,
            rag_hits,
            history=history,
            min_score=config.min_score,
        )

    return PipelineResult(
        question_ru=question_ru,
        question_en=question_en,
        retrieve_hits=hits,
        rag_hits=rag_hits,
        dropped=dropped,
        response=response,
    )
