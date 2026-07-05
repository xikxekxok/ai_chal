from __future__ import annotations

import os
import sys
from typing import Any

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"

_model: Any | None = None


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

    sticky_ids = {chunk_id for chunk_id in (sticky_chunk_ids or []) if chunk_id}
    sticky_source_ids: set[str] = set()
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
        if chunk_id in sticky_ids:
            score = max(score, sticky_floor)
            enriched["sticky"] = True
        enriched["rerank_score"] = score
        enriched["embed_score"] = float(item.get("score", 0.0))
        scored.append(enriched)

    scored.sort(key=lambda item: item["rerank_score"], reverse=True)

    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    kept_ids: set[str] = set()

    sticky_ranked = [
        item
        for item in scored
        if str(item.get("chunk_id", "")) in sticky_ids
    ]
    if sticky_ranked and top_k > 0:
        best_sticky = sticky_ranked[0]
        kept.append(best_sticky)
        kept_ids.add(str(best_sticky.get("chunk_id", "")))

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

    kept.sort(key=lambda item: item["rerank_score"], reverse=True)
    return kept, dropped
