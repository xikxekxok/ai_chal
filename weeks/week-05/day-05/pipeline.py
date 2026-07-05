from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from console_out import print_tagged
from history import SessionState, Turn
from query import QueryIntent, process_query
from rag import RagResponse, generate_with_rag
from rerank import rerank_filter
from retrieve import format_fusion_stats, retrieve_fusion, sticky_chunk_ids
from run_log import get_run_log


@dataclass
class PipelineConfig:
    retrieve_k: int = 20
    secondary_k: int = 10
    rag_k: int = 4
    min_score: float = 0.15


@dataclass
class PipelineResult:
    question_ru: str
    question_en: str
    is_follow_up: bool = False
    intent: QueryIntent = "follow_up"
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
    session: SessionState | None = None,
    generate_answer: bool = True,
) -> PipelineResult:
    log = get_run_log()
    turns = history or []
    session = session or SessionState()

    log.section("session_before")
    log.kv("last_standalone_query_en", session.last_standalone_query_en or "(empty)", indent=1)
    log.kv("last_chunk_ids", session.last_chunk_ids or "(empty)", indent=1)
    log.kv("recent_chunk_ids", session.recent_chunk_ids or "(empty)", indent=1)
    log.kv("history_turns", len(turns), indent=1)
    if turns:
        log.section("history_preview")
        for turn in turns[-6:]:
            preview = turn.content.replace("\n", " ")[:120]
            log.line(f"{turn.role}: {preview}", indent=1)
        log.blank()

    query_result = process_query(question_ru, history=turns, session=session)
    question_en = query_result.standalone_query_en
    use_sticky = query_result.intent != "new_topic"

    use_fusion = query_result.is_follow_up and use_sticky and (
        bool(session.last_standalone_query_en) or bool(sticky_chunk_ids(session))
    )
    log.section("retrieve_plan")
    log.kv("standalone_query_en", question_en, indent=1)
    log.kv("is_follow_up", query_result.is_follow_up, indent=1)
    log.kv("intent", query_result.intent, indent=1)
    log.kv("use_sticky", use_sticky, indent=1)
    log.kv("use_fusion", use_fusion, indent=1)
    if use_fusion:
        log.kv("secondary_query_en", session.last_standalone_query_en or "(empty)", indent=1)
        log.kv("sticky_chunk_ids", sticky_chunk_ids(session), indent=1)
    log.kv("primary_k", config.retrieve_k, indent=1)
    log.kv("secondary_k", config.secondary_k, indent=1)

    hits, stats = retrieve_fusion(
        question_en,
        is_follow_up=query_result.is_follow_up,
        use_sticky=use_sticky,
        session=session,
        chunks=chunks,
        primary_k=config.retrieve_k,
        secondary_k=config.secondary_k,
    )
    print_tagged("retrieve", format_fusion_stats(stats))
    log.section("retrieve_stats")
    for key, value in stats.items():
        log.kv(key, value, indent=1)
    log.hits("retrieve_hits", hits, limit=20)

    rag_hits, dropped = rerank_filter(
        question_en,
        hits,
        min_score=config.min_score,
        top_k=config.rag_k,
        sticky_chunk_ids=sticky_chunk_ids(session) if use_sticky else [],
    )
    kept_scores = [f"{h.get('rerank_score', 0):.3f}" for h in rag_hits[:3]]
    print_tagged(
        "rerank",
        f"kept={len(rag_hits)} dropped={len(dropped)} "
        f"min_score={config.min_score} top_scores=[{', '.join(kept_scores)}]",
    )
    log.section("rerank")
    log.kv("min_score", config.min_score, indent=1)
    log.kv("top_k", config.rag_k, indent=1)
    log.hits("rerank_kept", rag_hits, limit=10)
    log.hits("rerank_dropped", dropped[:15], limit=15)

    response: RagResponse | None = None
    if generate_answer:
        response = generate_with_rag(
            question_en,
            rag_hits,
            history=turns,
            min_score=config.min_score,
        )
        if response is not None:
            log.section("rag_result")
            log.kv("context_sufficient", response.context_sufficient, indent=1)
            log.kv("sources_count", len(response.sources), indent=1)
            log.kv("citations_count", len(response.citations), indent=1)
            if response.clarification_hint:
                log.kv("clarification_hint", response.clarification_hint, indent=1)
            log.block("answer", response.answer, max_chars=2000)
            if response.sources:
                log.json_block(
                    "sources",
                    [src.__dict__ for src in response.sources],
                )

    return PipelineResult(
        question_ru=question_ru,
        question_en=question_en,
        is_follow_up=query_result.is_follow_up,
        intent=query_result.intent,
        retrieve_hits=hits,
        rag_hits=rag_hits,
        dropped=dropped,
        response=response,
    )
