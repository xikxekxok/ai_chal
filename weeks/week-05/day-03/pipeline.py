from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from console_out import print_tagged
from rag import generate_with_rag
from rerank import rerank_filter
from retrieve import retrieve
from rewrite import rewrite_query
from translate import translate_to_en


class PipelineMode(StrEnum):
    BARE = "bare"
    REWRITE = "rewrite"
    RERANK = "rerank"
    BOTH = "both"


MODE_LABELS: dict[PipelineMode, str] = {
    PipelineMode.BARE: "голый RAG",
    PipelineMode.REWRITE: "rewrite без rerank",
    PipelineMode.RERANK: "rerank без rewrite",
    PipelineMode.BOTH: "rerank + rewrite",
}

ALL_MODES: tuple[PipelineMode, ...] = (
    PipelineMode.BARE,
    PipelineMode.REWRITE,
    PipelineMode.RERANK,
    PipelineMode.BOTH,
)


@dataclass
class PipelineConfig:
    mode: PipelineMode = PipelineMode.BOTH
    retrieve_k: int = 20
    rag_k: int = 4
    min_score: float = 0.15

    @property
    def use_rewrite(self) -> bool:
        return self.mode in (PipelineMode.REWRITE, PipelineMode.BOTH)

    @property
    def use_rerank(self) -> bool:
        return self.mode in (PipelineMode.RERANK, PipelineMode.BOTH)

    @classmethod
    def for_mode(cls, mode: PipelineMode) -> PipelineConfig:
        if mode in (PipelineMode.BARE, PipelineMode.REWRITE):
            return cls(mode=mode, retrieve_k=6, rag_k=6, min_score=0.0)
        return cls(mode=mode, retrieve_k=20, rag_k=4, min_score=0.15)

    def with_overrides(
        self,
        *,
        retrieve_k: int | None = None,
        rag_k: int | None = None,
        min_score: float | None = None,
        no_rewrite: bool = False,
        no_rerank: bool = False,
    ) -> PipelineConfig:
        cfg = PipelineConfig(
            mode=self.mode,
            retrieve_k=retrieve_k if retrieve_k is not None else self.retrieve_k,
            rag_k=rag_k if rag_k is not None else self.rag_k,
            min_score=min_score if min_score is not None else self.min_score,
        )
        if no_rewrite and no_rerank:
            cfg.mode = PipelineMode.BARE
        elif no_rewrite:
            cfg.mode = PipelineMode.RERANK
        elif no_rerank:
            cfg.mode = PipelineMode.REWRITE
        return cfg


@dataclass
class PipelineResult:
    question_ru: str
    question_en: str
    search_query_en: str
    mode: PipelineMode
    retrieve_hits: list[dict[str, Any]] = field(default_factory=list)
    rag_hits: list[dict[str, Any]] = field(default_factory=list)
    dropped: list[dict[str, Any]] = field(default_factory=list)
    answer: str | None = None


def run_pipeline(
    question_ru: str,
    chunks: list[dict[str, Any]],
    config: PipelineConfig,
    *,
    generate_answer: bool = True,
    question_en: str | None = None,
    search_query_en: str | None = None,
) -> PipelineResult:
    if question_en is None:
        question_en = translate_to_en(question_ru)

    if config.use_rewrite:
        if search_query_en is None:
            search_query_en = rewrite_query(question_en)
        query_for_retrieve = search_query_en
    else:
        query_for_retrieve = question_en

    hits = retrieve(query_for_retrieve, chunks, top_k=config.retrieve_k)

    rag_hits = hits
    dropped: list[dict[str, Any]] = []
    if config.use_rerank:
        rag_hits, dropped = rerank_filter(
            query_for_retrieve,
            hits,
            min_score=config.min_score,
            top_k=config.rag_k,
        )
    else:
        rag_hits = hits[: config.rag_k]

    answer: str | None = None
    if generate_answer:
        answer = generate_with_rag(question_en, rag_hits)
        label = MODE_LABELS[config.mode]
        print_tagged("rag", f"{label} · chunks={len(rag_hits)}")

    return PipelineResult(
        question_ru=question_ru,
        question_en=question_en,
        search_query_en=query_for_retrieve,
        mode=config.mode,
        retrieve_hits=hits,
        rag_hits=rag_hits,
        dropped=dropped,
        answer=answer,
    )
