"""Человекочитаемый вывод tool calls и раскрытие результатов (дело Тофика)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from console_out import print_block, print_tagged

DAY_DIR = Path(__file__).resolve().parent
SUSPECTS_PATH = DAY_DIR / "data" / "case" / "suspects.json"

PAGE_PREVIEW_CHARS = 500
_suspect_names: dict[str, str] | None = None

FILE_LABELS = {
    "yard_report": ("report", "Отчёт енота Лестрейда"),
    "witness_marta": ("witness", "Показания Марты"),
    "gazebo_log": ("witness", "Журнал у беседки"),
    "shed_findings": ("report", "Осмотр сарая и амбара"),
    "suspects": ("dossier", "Список подозреваемых (файл)"),
}


def _load_suspect_names() -> dict[str, str]:
    global _suspect_names
    if _suspect_names is not None:
        return _suspect_names
    names: dict[str, str] = {}
    if SUSPECTS_PATH.is_file():
        data = json.loads(SUSPECTS_PATH.read_text(encoding="utf-8"))
        for item in data.get("suspects") or []:
            if isinstance(item, dict) and item.get("id"):
                names[str(item["id"])] = str(item.get("name") or item["id"])
    _suspect_names = names
    return names


def suspect_label(suspect_id: str) -> str:
    return _load_suspect_names().get(suspect_id, suspect_id)


def _clip(text: str, limit: int = 90) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _format_suspects(suspects: list[Any]) -> str:
    lines: list[str] = []
    for index, item in enumerate(suspects, start=1):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("id") or "?")
        motive = str(item.get("motive") or "—")
        alibi = str(item.get("alibi") or "—")
        lines.append(f"{index}. {name}")
        lines.append(f"   Мотив: {motive}")
        lines.append(f"   Алиби: {alibi}")
        lines.append("")
    return "\n".join(lines).rstrip()


def reveal_tool_result(
    server: str,
    tool: str,
    payload: dict[str, Any],
    *,
    arguments: dict[str, Any] | None = None,
) -> None:
    """Полный человекочитаемый вывод результата tool (без JSON-дампа)."""
    if "error" in payload:
        print_tagged("error", str(payload["error"]))
        return

    args = arguments or {}

    if tool == "list_case_files":
        lines = [f"Дело: {payload.get('case_id')} | жертва: {payload.get('victim')}", ""]
        for item in payload.get("files") or []:
            if isinstance(item, dict):
                lines.append(f"  • {item.get('title')} ({item.get('id')})")
        print_block("archive", "Архив норы", "\n".join(lines))
        return

    if tool == "read_case_file":
        fid = str(payload.get("file_id") or args.get("file_id") or "")
        tag, title = FILE_LABELS.get(fid, ("document", fid))
        content = payload.get("content")
        if payload.get("format") == "markdown" and isinstance(content, str):
            print_block(tag, title, content)
        elif payload.get("format") == "json" and isinstance(content, dict):
            body = _format_suspects(content.get("suspects") or [])
            print_block(tag, title, body)
        return

    if tool == "list_suspects":
        body = _format_suspects(payload.get("suspects") or [])
        print_block("dossier", "Досье подозреваемых", body)
        return

    if tool == "add_clue":
        clue = payload.get("clue") if isinstance(payload.get("clue"), dict) else {}
        total = payload.get("total", "?")
        tags = ", ".join(clue.get("tags") or [])
        body = (
            f"№{total}\n"
            f"Факт: {clue.get('fact', args.get('fact', ''))}\n"
            f"Источник: {clue.get('source', args.get('source', ''))}\n"
            f"Теги: {tags or '—'}"
        )
        print_block("clue", "Улика на доске", body)
        return

    if tool == "list_clues":
        clues = payload.get("clues") or []
        lines: list[str] = []
        for clue in clues:
            if not isinstance(clue, dict):
                continue
            tags = ", ".join(clue.get("tags") or [])
            lines.append(f"• [{clue.get('id')}] {clue.get('fact')}")
            lines.append(f"  источник: {clue.get('source')} | теги: {tags or '—'}")
            lines.append("")
        print_block("clue", f"Доска улик ({payload.get('count', len(clues))})", "\n".join(lines))
        return

    if tool == "build_timeline":
        lines: list[str] = []
        for event in payload.get("events") or []:
            if isinstance(event, dict):
                lines.append(f"  {event.get('time')} — {event.get('fact')}")
        print_block("clue", "Хронология", "\n".join(lines) if lines else "(пусто)")
        return

    if tool == "web_search":
        query = str(payload.get("query") or "")
        lines = [f"Запрос: «{query}»", ""]
        for index, item in enumerate(payload.get("results") or [], start=1):
            if not isinstance(item, dict):
                continue
            title = item.get("title") or "?"
            url = str(item.get("url") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            if len(snippet) > 280:
                snippet = snippet[:279] + "…"
            lines.append(f"{index}. {title}")
            if url:
                lines.append(f"   {url}")
            if snippet:
                lines.append(f"   {snippet}")
            lines.append("")
        body = "\n".join(lines).rstrip()
        print_block("trail", f"Поиск в сети ({payload.get('count', 0)})", body)
        return

    if tool == "read_page":
        text = str(payload.get("text") or "")
        truncated = bool(payload.get("truncated"))
        url = str(payload.get("url") or "")
        if len(text) > PAGE_PREVIEW_CHARS:
            text = text[:PAGE_PREVIEW_CHARS] + "…"
        title = payload.get("title") or "страница"
        header = f"{title}"
        if url:
            header += f"\n{url}"
        note = " (текст обрезан для stdout)" if truncated else ""
        print_block("trail", f"Страница{note}", f"{header}\n\n{text}" if text else header)
        return

    if tool == "test_theory":
        verdict = str(payload.get("verdict") or "")
        name = str(payload.get("suspect_name") or "")
        reason = str(payload.get("reason") or "")
        labels = {"supported": "ПОДТВЕРЖДЕНО", "weak": "СЛАБО", "busted": "ОТБРОШЕНО"}
        body = f"{name}: {labels.get(verdict, verdict)}\n{reason}"
        print_block("deduction", "Проверка версии", body)
        return

    if tool == "accuse":
        if payload.get("ok"):
            body = (
                f"Виновен: {payload.get('suspect_name')}\n"
                f"{payload.get('reason')}\n"
                f"Улик: {payload.get('clue_count')} | жертва: {payload.get('victim')}"
            )
            print_block("verdict", "Обвинение", body)
        return


def format_mcp_call(tool: str, args: dict[str, Any]) -> str:
    """Краткая строка вызова без дублирования полного содержимого reveal-блоков."""
    if tool == "add_clue":
        return "add_clue(...)"
    if tool == "read_case_file":
        return f'read_case_file(file_id={args.get("file_id")!r})'
    if tool == "web_search":
        q = _clip(str(args.get("query") or ""), 70)
        return f'web_search(query="{q}")'
    if tool == "read_page":
        url = _clip(str(args.get("url") or ""), 70)
        return f'read_page(url="{url}")'
    if tool in {"test_theory", "accuse"}:
        sid = args.get("suspect_id") or "?"
        return f'{tool}(suspect_id={sid!r})'
    if tool in {"list_case_files", "list_suspects", "list_clues", "build_timeline", "clear_clues"}:
        return f"{tool}()"
    return tool
