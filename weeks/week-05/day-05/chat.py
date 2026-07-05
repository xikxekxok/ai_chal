from __future__ import annotations

from typing import Any

from console_out import print_section, print_tagged
from history import SourceRecord, Turn, clear_history, load_history, save_history
from paths import HISTORY_PATH
from pipeline import PipelineConfig, PipelineResult, run_pipeline
from rag import (
    RagResponse,
    format_citations,
    format_rag_summary,
    format_sources,
)


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
        self._turns = load_history(history_path)

    @property
    def turn_count(self) -> int:
        return len(self._turns)

    @property
    def history_path(self):
        return self._history_path

    def clear(self) -> None:
        clear_history(self._history_path)
        self._turns = []

    def run_turn(self, question_ru: str) -> PipelineResult:
        print_section("user", question_ru)
        result = run_pipeline(
            question_ru,
            self._chunks,
            self._config,
            history=self._turns,
        )
        if result.response is not None:
            self._append_turn(question_ru, result.response)
        return result

    def _append_turn(self, question_ru: str, response: RagResponse) -> None:
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
        save_history(self._turns, self._history_path)


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
