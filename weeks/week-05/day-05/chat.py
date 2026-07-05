from __future__ import annotations

from typing import Any

from console_out import print_section, print_tagged
from history import (
    SessionState,
    SourceRecord,
    Turn,
    clear_history,
    load_chat_state,
    merge_recent_chunk_ids,
    save_chat_state,
)
from paths import HISTORY_PATH
from pipeline import PipelineConfig, PipelineResult, run_pipeline
from rag import (
    format_citations,
    format_rag_summary,
    format_sources,
)
from run_log import get_run_log


class RagChat:
    def __init__(
        self,
        chunks: list[dict[str, Any]],
        config: PipelineConfig,
        *,
        history_path=HISTORY_PATH,
    ) -> None:
        self._chunks = chunks
        self._config = config
        self._history_path = history_path
        self._turns, self._session = load_chat_state(history_path)
        self._turn_num = 0

    @property
    def turn_count(self) -> int:
        return len(self._turns)

    @property
    def history_path(self):
        return self._history_path

    def clear(self) -> None:
        clear_history(self._history_path)
        self._turns = []
        self._session = SessionState()
        self._turn_num = 0

    def run_turn(self, question_ru: str) -> PipelineResult:
        self._turn_num += 1
        get_run_log().turn_start(self._turn_num, question_ru)
        print_section("user", question_ru)
        result = run_pipeline(
            question_ru,
            self._chunks,
            self._config,
            history=self._turns,
            session=self._session,
        )
        if result.response is not None:
            self._append_turn(question_ru, result)
            log = get_run_log()
            log.section("session_after")
            log.kv("last_standalone_query_en", self._session.last_standalone_query_en, indent=1)
            log.kv("last_chunk_ids", self._session.last_chunk_ids, indent=1)
            log.kv("recent_chunk_ids", self._session.recent_chunk_ids, indent=1)
            log.kv("turns_saved", len(self._turns), indent=1)
            log.blank()
        return result

    def _append_turn(self, question_ru: str, result: PipelineResult) -> None:
        response = result.response
        assert response is not None

        self._turns.append(Turn(role="user", content=question_ru))
        sources = [
            SourceRecord(
                source_id=src.source_id,
                title=src.title,
                section=src.section,
                chunk_id=src.chunk_id,
            )
            for src in response.sources
        ]
        self._turns.append(
            Turn(
                role="assistant",
                content=response.answer,
                sources=sources,
                context_sufficient=response.context_sufficient,
            )
        )
        new_chunk_ids = [src.chunk_id for src in response.sources if src.chunk_id]
        if not new_chunk_ids and result.rag_hits:
            new_chunk_ids = [
                str(hit.get("chunk_id", ""))
                for hit in result.rag_hits
                if hit.get("chunk_id")
            ]
        self._session = SessionState(
            last_standalone_query_en=result.question_en,
            last_base_query_en=result.base_query_en,
            last_chunk_ids=new_chunk_ids,
            recent_chunk_ids=merge_recent_chunk_ids(
                self._session.recent_chunk_ids,
                new_chunk_ids,
            ),
        )
        save_chat_state(self._turns, self._session, self._history_path)


def print_response(result: PipelineResult) -> None:
    if result.response is None:
        return
    resp = result.response
    print_tagged("rag", format_rag_summary(resp))
    print_section("agent", resp.answer)
    print_section("sources", format_sources(resp.sources), layout="block")
    print_section("citations", format_citations(resp.citations), layout="block")
    if resp.clarification_hint:
        print_tagged("rag", f"clarification_hint: {resp.clarification_hint}")
