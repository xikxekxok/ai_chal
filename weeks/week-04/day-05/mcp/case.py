"""Чтение seed-файлов дела missing_ball."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DAY_DIR = Path(__file__).resolve().parents[1]
CASE_DIR = DAY_DIR / "data" / "case"

ALLOWED_FILES = frozenset(
    {"yard_report", "witness_marta", "gazebo_log", "shed_findings", "suspects"}
)

# Частые ошибки LLM — маппим на канонический id.
FILE_ALIASES: dict[str, str] = {
    "shed_survey": "shed_findings",
    "shed_inspection": "shed_findings",
    "gazebo": "gazebo_log",
}


def list_case_files() -> dict[str, Any]:
    files: list[dict[str, str]] = []
    for name in sorted(ALLOWED_FILES):
        if name == "suspects":
            path = CASE_DIR / "suspects.json"
            kind = "json"
        else:
            path = CASE_DIR / f"{name}.md"
            kind = "markdown"
        if path.is_file():
            files.append({"id": name, "kind": kind, "title": _title_for(name)})
    return {"case_id": "missing_ball", "victim": "Тофик", "files": files}


def _title_for(file_id: str) -> str:
    titles = {
        "yard_report": "Отчёт енота Лестрейда",
        "witness_marta": "Показания Марты",
        "gazebo_log": "Журнал у беседки",
        "shed_findings": "Осмотр сарая и амбара",
        "suspects": "Список подозреваемых",
    }
    return titles.get(file_id, file_id)


def read_case_file(file_id: str) -> dict[str, Any]:
    file_id = file_id.strip().removesuffix(".md").removesuffix(".json")
    file_id = FILE_ALIASES.get(file_id, file_id)
    if file_id not in ALLOWED_FILES:
        allowed = ", ".join(sorted(ALLOWED_FILES))
        raise ValueError(f"unknown case file: {file_id!r}; allowed: {allowed}")

    if file_id == "suspects":
        path = CASE_DIR / "suspects.json"
        if not path.is_file():
            raise ValueError("suspects.json not found")
        data = json.loads(path.read_text(encoding="utf-8"))
        return {"file_id": file_id, "format": "json", "content": data}

    path = CASE_DIR / f"{file_id}.md"
    if not path.is_file():
        raise ValueError(f"{file_id}.md not found")
    text = path.read_text(encoding="utf-8")
    return {"file_id": file_id, "format": "markdown", "content": text, "chars": len(text)}


def list_suspects() -> dict[str, Any]:
    path = CASE_DIR / "suspects.json"
    if not path.is_file():
        raise ValueError("suspects.json not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "case_id": data.get("case_id", "missing_ball"),
        "victim": data.get("victim", "Тофик"),
        "suspects": data.get("suspects") or [],
    }


def suspect_name(suspect_id: str) -> str:
    data = list_suspects()
    for item in data.get("suspects") or []:
        if isinstance(item, dict) and item.get("id") == suspect_id:
            return str(item.get("name") or suspect_id)
    return suspect_id
