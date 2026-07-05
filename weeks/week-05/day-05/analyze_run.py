#!/usr/bin/env python3
"""Summarize per-run logs and chat_history for RAG failure signals."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from paths import DAY_DIR, HISTORY_PATH, LOGS_DIR

TURN_RE = re.compile(r"^TURN (\d+)$", re.MULTILINE)
USER_RU_RE = re.compile(r"^user_ru: (.+)$", re.MULTILINE)
SCENARIO_START_RE = re.compile(
    r"\[scenario_start\]\n(?:  .+\n)*?  key: (\d+)",
    re.MULTILINE,
)
INSUFFICIENT_MARKERS = (
    re.compile(r"не\s+знаю", re.IGNORECASE),
    re.compile(r"don'?t know", re.IGNORECASE),
    re.compile(r"no (?:direct )?access", re.IGNORECASE),
    re.compile(r"нет (?:доступа|информации|данных)", re.IGNORECASE),
)


@dataclass
class TurnReport:
    turn_num: int
    user_ru: str
    scenario_key: str | None = None
    context_sufficient: bool | None = None
    sources_count: int | None = None
    answer_preview: str = ""
    flags: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.flags


def latest_log() -> Path | None:
    logs = sorted(LOGS_DIR.glob("*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
    return logs[0] if logs else None


def _scenario_at(text: str, turn_start: int) -> str | None:
    prefix = text[:turn_start]
    matches = list(SCENARIO_START_RE.finditer(prefix))
    return matches[-1].group(1) if matches else None


def _extract_block(section: str, text: str) -> str:
    match = re.search(rf"\[{section}\]\n(.*?)(?=\n\[|\n={3,}|\Z)", text, re.DOTALL)
    if not match:
        return ""
    lines: list[str] = []
    for line in match.group(1).splitlines():
        if line.startswith("  "):
            lines.append(line[2:])
        elif not line.strip():
            break
        else:
            lines.append(line)
    return "\n".join(lines).strip()


def _parse_bool(value: str) -> bool | None:
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    return None


def _flag_turn(report: TurnReport) -> None:
    if report.context_sufficient is False:
        report.flags.append("context_sufficient=false")
    if report.sources_count == 0:
        report.flags.append("sources_count=0")
    if not report.answer_preview.strip():
        report.flags.append("empty_answer")
    for pattern in INSUFFICIENT_MARKERS:
        if pattern.search(report.answer_preview):
            report.flags.append(f"text:{pattern.pattern}")
            break


def parse_log(path: Path) -> tuple[str, list[TurnReport]]:
    text = path.read_text(encoding="utf-8")
    mode_match = re.search(r"^mode: (.+)$", text, re.MULTILINE)
    mode = mode_match.group(1).strip() if mode_match else "unknown"

    turn_starts = list(TURN_RE.finditer(text))
    reports: list[TurnReport] = []
    for index, turn_match in enumerate(turn_starts):
        turn_num = int(turn_match.group(1))
        start = turn_match.start()
        end = turn_starts[index + 1].start() if index + 1 < len(turn_starts) else len(text)
        chunk = text[start:end]

        user_match = USER_RU_RE.search(chunk)
        user_ru = user_match.group(1).strip() if user_match else "?"

        rag_block = _extract_block("rag_result", chunk)
        context_sufficient: bool | None = None
        sources_count: int | None = None
        for line in rag_block.splitlines():
            if line.startswith("context_sufficient:"):
                context_sufficient = _parse_bool(line.split(":", 1)[1])
            elif line.startswith("sources_count:"):
                try:
                    sources_count = int(line.split(":", 1)[1].strip())
                except ValueError:
                    sources_count = None

        answer = _extract_block("answer", chunk)
        preview = answer.replace("\n", " ")[:120]

        report = TurnReport(
            turn_num=turn_num,
            user_ru=user_ru,
            scenario_key=_scenario_at(text, start),
            context_sufficient=context_sufficient,
            sources_count=sources_count,
            answer_preview=preview,
        )
        _flag_turn(report)
        reports.append(report)

    return mode, reports


def parse_history(path: Path = HISTORY_PATH) -> list[TurnReport]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    turns = data.get("turns", [])
    reports: list[TurnReport] = []
    turn_num = 0
    pending_user: str | None = None
    for item in turns:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        if role == "user":
            pending_user = str(item.get("content", ""))
            continue
        if role != "assistant":
            continue
        turn_num += 1
        answer = str(item.get("content", ""))
        sources = item.get("sources", [])
        sufficient = item.get("context_sufficient")
        report = TurnReport(
            turn_num=turn_num,
            user_ru=pending_user or "?",
            context_sufficient=sufficient if isinstance(sufficient, bool) else None,
            sources_count=len(sources) if isinstance(sources, list) else 0,
            answer_preview=answer.replace("\n", " ")[:120],
        )
        _flag_turn(report)
        reports.append(report)
        pending_user = None
    return reports


def _print_reports(source: str, reports: list[TurnReport]) -> int:
    print(f"=== analyze: {source} ===")
    if not reports:
        print("(no turns)")
        print()
        return 0

    failures = 0
    for report in reports:
        scenario = f" scenario={report.scenario_key}" if report.scenario_key else ""
        sufficient = report.context_sufficient
        status = "OK" if report.ok else "FAIL"
        if not report.ok:
            failures += 1
        print(f"{status} turn {report.turn_num}{scenario}: {report.user_ru[:80]}")
        print(
            f"  context_sufficient={sufficient} "
            f"sources={report.sources_count} "
            f"preview={report.answer_preview!r}"
        )
        if report.flags:
            print(f"  flags: {', '.join(report.flags)}")
    print(f"Summary: {failures} failures / {len(reports)} turns")
    print()
    return failures


def run_analysis(
    *,
    log_path: Path | None = None,
    history: bool = False,
    history_only: bool = False,
) -> int:
    total_failures = 0

    if not history_only:
        path = log_path
        if path is None:
            path = latest_log()
            if path is None:
                print(f"[error] no logs in {LOGS_DIR.relative_to(DAY_DIR)}", file=sys.stderr)
                return 2
        if not path.is_file():
            print(f"[error] log not found: {path}", file=sys.stderr)
            return 2
        _, reports = parse_log(path)
        rel = path.relative_to(DAY_DIR) if path.is_relative_to(DAY_DIR) else path
        total_failures += _print_reports(str(rel), reports)

    if history or history_only:
        history_reports = parse_history()
        rel_history = HISTORY_PATH.relative_to(DAY_DIR)
        total_failures += _print_reports(str(rel_history), history_reports)

    return 1 if total_failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze RAG run logs and chat history.")
    parser.add_argument(
        "log_path",
        nargs="?",
        type=Path,
        help="Path to a run log (default: latest in logs/).",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="Also analyze chat_history.json.",
    )
    parser.add_argument(
        "--history-only",
        action="store_true",
        help="Analyze chat_history.json only (skip log file).",
    )
    args = parser.parse_args()
    sys.exit(
        run_analysis(
            log_path=args.log_path,
            history=args.history,
            history_only=args.history_only,
        )
    )


if __name__ == "__main__":
    main()
