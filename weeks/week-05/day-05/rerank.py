from __future__ import annotations

import os
import sys
from typing import Any

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"
ECOLOGY_SOURCE_ID = "37199"
ECOLOGY_DRIFT_PENALTY = 0.08

_model: Any | None = None


def _sticky_tie_key(chunk_id: str, sticky_chunk_ids: list[str]) -> tuple[int, int]:
    try:
        sticky_order = sticky_chunk_ids.index(chunk_id)
    except ValueError:
        sticky_order = len(sticky_chunk_ids)
    try:
        _, idx_part = chunk_id.split(":", 1)
        chunk_idx = int(idx_part, 10)
    except (ValueError, AttributeError):
        chunk_idx = 0
    return sticky_order, -chunk_idx


def _sort_key(
    item: dict[str, Any],
    *,
    sticky_chunk_ids: list[str],
    sticky_ids: set[str],
    sticky_floor: float,
) -> tuple[float, int, int]:
    score = float(item["rerank_score"])
    chunk_id = str(item.get("chunk_id", ""))
    if chunk_id in sticky_ids and abs(score - sticky_floor) < 1e-6:
        order, neg_idx = _sticky_tie_key(chunk_id, sticky_chunk_ids)
        return -score, order, neg_idx
    return -score, 0, 0


def _load_model() -> Any:
    global _model
    if _model is not None:
        return _model
    try:
        import torch
        from sentence_transformers import CrossEncoder
    except ImportError as exc:
        print(
            "[error] sentence-transformers не установлен — "
            "pip install -r weeks/week-05/day-05/requirements.txt",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    _model = CrossEncoder(DEFAULT_MODEL, activation_fn=torch.nn.Sigmoid())
    return _model


def rerank_filter(
    query_en: str,
    candidates: list[dict[str, Any]],
    *,
    min_score: float,
    top_k: int,
    sticky_chunk_ids: list[str] | None = None,
    sticky_floor: float = 0.12,
    source_boost: float = 0.03,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not candidates:
        return [], []

    sticky_list = [chunk_id for chunk_id in (sticky_chunk_ids or []) if chunk_id]
    sticky_ids = set(sticky_list)
    sticky_source_ids: set[str] = set()
    ecology_drift = False
    if sticky_list:
        non_ecology = sum(
            1 for chunk_id in sticky_list if not chunk_id.startswith(f"{ECOLOGY_SOURCE_ID}:")
        )
        ecology_drift = non_ecology / len(sticky_list) >= 0.5
    for item in candidates:
        chunk_id = str(item.get("chunk_id", ""))
        if chunk_id in sticky_ids:
            source_id = str(item.get("source_id", ""))
            if source_id:
                sticky_source_ids.add(source_id)

    model = _load_model()
    pairs = [(query_en, item.get("text") or "") for item in candidates]
    scores = model.predict(pairs, show_progress_bar=False)

    scored: list[dict[str, Any]] = []
    for item, rerank_score in zip(candidates, scores, strict=True):
        enriched = dict(item)
        score = float(rerank_score)
        chunk_id = str(item.get("chunk_id", ""))
        source_id = str(item.get("source_id", ""))
        if source_id and source_id in sticky_source_ids:
            score += source_boost
        if ecology_drift and source_id == ECOLOGY_SOURCE_ID:
            score -= ECOLOGY_DRIFT_PENALTY
        if chunk_id in sticky_ids:
            score = max(score, sticky_floor)
            enriched["sticky"] = True
        enriched["rerank_score"] = score
        enriched["embed_score"] = float(item.get("score", 0.0))
        scored.append(enriched)

    def sort_key(item: dict[str, Any]) -> tuple[float, int, int]:
        return _sort_key(
            item,
            sticky_chunk_ids=sticky_list,
            sticky_ids=sticky_ids,
            sticky_floor=sticky_floor,
        )

    scored.sort(key=sort_key)

    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    kept_ids: set[str] = set()

    sticky_ranked = [
        item
        for item in scored
        if str(item.get("chunk_id", "")) in sticky_ids
    ]
    if sticky_ranked and top_k > 0:
        all_sticky_at_floor = all(
            abs(float(item["rerank_score"]) - sticky_floor) < 1e-6 for item in sticky_ranked
        )
        sticky_slots = min(2 if all_sticky_at_floor else 1, top_k, len(sticky_ranked))
        sticky_ranked.sort(key=sort_key)
        for item in sticky_ranked[:sticky_slots]:
            chunk_id = str(item.get("chunk_id", ""))
            kept.append(item)
            kept_ids.add(chunk_id)

    for item in scored:
        chunk_id = str(item.get("chunk_id", ""))
        if chunk_id in kept_ids:
            continue
        if item["rerank_score"] >= min_score and len(kept) < top_k:
            kept.append(item)
            kept_ids.add(chunk_id)
        else:
            dropped.append(item)

    for item in scored:
        chunk_id = str(item.get("chunk_id", ""))
        if chunk_id not in kept_ids and item not in dropped:
            dropped.append(item)

    kept.sort(key=sort_key)
    return kept, dropped
