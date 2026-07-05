from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from paths import HISTORY_PATH


@dataclass
class SourceRecord:
    source_id: str
    title: str
    section: str
    chunk_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "section": self.section,
            "chunk_id": self.chunk_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceRecord:
        return cls(
            source_id=str(data.get("source_id", "")),
            title=str(data.get("title", "")),
            section=str(data.get("section", "")),
            chunk_id=str(data.get("chunk_id", "")),
        )


RECENT_CHUNK_CAP = 12


@dataclass
class SessionState:
    last_standalone_query_en: str = ""
    last_base_query_en: str = ""
    last_chunk_ids: list[str] = field(default_factory=list)
    recent_chunk_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_standalone_query_en": self.last_standalone_query_en,
            "last_base_query_en": self.last_base_query_en,
            "last_chunk_ids": list(self.last_chunk_ids),
            "recent_chunk_ids": list(self.recent_chunk_ids),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SessionState:
        if not isinstance(data, dict):
            return cls()
        raw_ids = data.get("last_chunk_ids", [])
        chunk_ids = [str(item) for item in raw_ids if item] if isinstance(raw_ids, list) else []
        raw_recent = data.get("recent_chunk_ids", [])
        recent_ids = (
            [str(item) for item in raw_recent if item] if isinstance(raw_recent, list) else []
        )
        if not recent_ids and chunk_ids:
            recent_ids = list(chunk_ids)
        return cls(
            last_standalone_query_en=str(data.get("last_standalone_query_en", "")),
            last_base_query_en=str(data.get("last_base_query_en", "")),
            last_chunk_ids=chunk_ids,
            recent_chunk_ids=recent_ids,
        )


def merge_recent_chunk_ids(
    existing: list[str],
    new_ids: list[str],
    *,
    cap: int = RECENT_CHUNK_CAP,
) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for chunk_id in [*new_ids, *existing]:
        if not chunk_id or chunk_id in seen:
            continue
        seen.add(chunk_id)
        merged.append(chunk_id)
        if len(merged) >= cap:
            break
    return merged


@dataclass
class Turn:
    role: str
    content: str
    sources: list[SourceRecord] = field(default_factory=list)
    context_sufficient: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        item: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.role == "assistant":
            item["sources"] = [src.to_dict() for src in self.sources]
            if self.context_sufficient is not None:
                item["context_sufficient"] = self.context_sufficient
        return item

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Turn:
        sources = [
            SourceRecord.from_dict(item)
            for item in data.get("sources", [])
            if isinstance(item, dict)
        ]
        sufficient = data.get("context_sufficient")
        return cls(
            role=str(data.get("role", "")),
            content=str(data.get("content", "")),
            sources=sources,
            context_sufficient=sufficient if isinstance(sufficient, bool) else None,
        )


def _load_turns(data: dict[str, Any]) -> list[Turn]:
    turns_raw = data.get("turns", [])
    if not isinstance(turns_raw, list):
        return []
    return [Turn.from_dict(item) for item in turns_raw if isinstance(item, dict)]


def load_history(path: Path = HISTORY_PATH) -> list[Turn]:
    turns, _session = load_chat_state(path)
    return turns


def load_chat_state(path: Path = HISTORY_PATH) -> tuple[list[Turn], SessionState]:
    if not path.is_file():
        return [], SessionState()
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return [], SessionState()
    session_raw = data.get("session")
    session = SessionState.from_dict(session_raw if isinstance(session_raw, dict) else None)
    return _load_turns(data), session


def save_history(turns: list[Turn], path: Path = HISTORY_PATH) -> None:
    save_chat_state(turns, SessionState(), path)


def save_chat_state(
    turns: list[Turn],
    session: SessionState,
    path: Path = HISTORY_PATH,
) -> None:
    payload = {
        "turns": [turn.to_dict() for turn in turns],
        "session": session.to_dict(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def clear_history(path: Path = HISTORY_PATH) -> None:
    if path.is_file():
        path.unlink()


def history_for_llm(turns: list[Turn], *, max_turns: int = 10) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for turn in turns[-max_turns:]:
        if turn.role in {"user", "assistant"} and turn.content.strip():
            messages.append({"role": turn.role, "content": turn.content})
    return messages


def history_for_translate(turns: list[Turn], *, max_pairs: int = 4) -> list[Turn]:
    return turns[-(max_pairs * 2) :]
