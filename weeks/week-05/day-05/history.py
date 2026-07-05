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


def load_history(path: Path = HISTORY_PATH) -> list[Turn]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    turns_raw = data.get("turns", [])
    if not isinstance(turns_raw, list):
        return []
    return [Turn.from_dict(item) for item in turns_raw if isinstance(item, dict)]


def save_history(turns: list[Turn], path: Path = HISTORY_PATH) -> None:
    payload = {"turns": [turn.to_dict() for turn in turns]}
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
