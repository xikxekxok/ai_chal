"""Формирование отчёта и сохранение заметок на диск."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

DAY_DIR = Path(__file__).resolve().parents[1]
NOTES_DIR = DAY_DIR / "data" / "notes"

_SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")


def _sanitize_filename(filename: str) -> str:
    name = Path(filename.strip()).name
    if not name or name in {".", ".."}:
        raise ValueError("filename must not be empty")
    if ".." in filename or "/" in filename or "\\" in filename:
        raise ValueError("filename must be a basename without path separators")
    if not name.endswith(".md"):
        name = f"{name}.md"
    safe = _SAFE_NAME.sub("_", name)
    if not safe.endswith(".md"):
        safe = f"{safe}.md"
    return safe


def _format_sources(sources: list[dict[str, Any]] | None) -> str:
    if not sources:
        return "_Источники не указаны._"
    lines: list[str] = []
    for item in sources:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "source").strip()
        url = str(item.get("url") or "").strip()
        if url:
            lines.append(f"- [{title}]({url})")
        elif title:
            lines.append(f"- {title}")
    return "\n".join(lines) if lines else "_Источники не указаны._"


def build_report(
    topic: str,
    findings: str,
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, object]:
    topic = topic.strip()
    findings = findings.strip()
    if not topic:
        raise ValueError("topic must not be empty")
    if not findings:
        raise ValueError("findings must not be empty")

    markdown = (
        f"# {topic}\n\n"
        f"## Итог\n\n"
        f"{findings}\n\n"
        f"## Источники\n\n"
        f"{_format_sources(sources)}\n"
    )
    return {"topic": topic, "markdown": markdown, "char_count": len(markdown)}


def save_note(filename: str, content: str) -> dict[str, object]:
    content = content.strip()
    if not content:
        raise ValueError("content must not be empty")

    safe_name = _sanitize_filename(filename)
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    path = NOTES_DIR / safe_name
    path.write_text(content, encoding="utf-8")
    rel = path.relative_to(DAY_DIR)
    return {"ok": True, "path": str(rel), "bytes": path.stat().st_size}
