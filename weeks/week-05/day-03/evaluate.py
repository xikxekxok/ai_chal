"""LLM-based accuracy scoring for demo answers."""

from __future__ import annotations

import json
import re
from typing import Any

from console_out import print_section
from llm import complete
from pipeline import MODE_LABELS, PipelineMode

EVAL_SYSTEM = (
    "You evaluate RAG system answers for factual accuracy.\n"
    "Compare each candidate answer to the reference answer on the same question.\n"
    "Score each candidate from 0.0 (wrong or no overlap) to 1.0 (fully accurate, all key facts).\n"
    "Partial credit when most key facts are present but some details are missing.\n"
    "Ignore style and citation phrasing — judge factual content only.\n"
    "Return ONLY valid JSON with mode keys, no markdown:\n"
    '{"bare": 0.0, "rewrite": 0.0, "rerank": 0.0, "both": 0.0}'
)


def _build_eval_user(
    question_ru: str,
    expect_ru: str,
    answers: dict[PipelineMode, str],
) -> str:
    parts = [
        f"Question (Russian):\n{question_ru}\n",
        f"Reference answer (Russian):\n{expect_ru}\n",
        "Candidate answers:",
    ]
    for mode, answer in answers.items():
        label = MODE_LABELS[mode]
        text = answer.strip() or "(empty answer)"
        parts.append(f"\n--- {mode.value} ({label}) ---\n{text}")
    return "\n".join(parts)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        data = json.loads(match.group())
        if isinstance(data, dict):
            return data
    raise ValueError(f"Cannot parse evaluator JSON: {text[:200]}")


def _clamp_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, score))


def _lookup_score(parsed: dict[str, Any], mode: PipelineMode) -> Any:
    if mode.value in parsed:
        return parsed[mode.value]
    nested = parsed.get("scores")
    if isinstance(nested, dict):
        return nested.get(mode.value)
    return None


def evaluate_answers(
    question_ru: str,
    expect_ru: str,
    answers: dict[PipelineMode, str],
) -> dict[PipelineMode, float]:
    result = complete(
        [
            {"role": "system", "content": EVAL_SYSTEM},
            {
                "role": "user",
                "content": _build_eval_user(question_ru, expect_ru, answers),
            },
        ],
        temperature=0,
    )
    parsed = _extract_json(result)
    return {mode: _clamp_score(_lookup_score(parsed, mode)) for mode in answers}


def print_rating(scores: dict[PipelineMode, float]) -> None:
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    lines = [
        f"{rank}. {MODE_LABELS[mode]} · {score:.2f}"
        for rank, (mode, score) in enumerate(ranked, 1)
    ]
    print_section("rating", "\n".join(lines), layout="block")


def print_total_rating(all_scores: dict[PipelineMode, list[float]]) -> None:
    averages = {
        mode: sum(values) / len(values)
        for mode, values in all_scores.items()
        if values
    }
    if not averages:
        return
    ranked = sorted(averages.items(), key=lambda item: item[1], reverse=True)
    n = max(len(values) for values in all_scores.values())
    lines = [
        f"{rank}. {MODE_LABELS[mode]} · {avg:.2f} (среднее за {n} вопросов)"
        for rank, (mode, avg) in enumerate(ranked, 1)
    ]
    winner_mode, winner_avg = ranked[0]
    lines.append("")
    lines.append(f"победитель: {MODE_LABELS[winner_mode]} · {winner_avg:.2f}")
    print_section("total-rating", "\n".join(lines), layout="block")
