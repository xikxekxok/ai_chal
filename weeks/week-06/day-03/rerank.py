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
            "pip install -r weeks/week-06/day-03/requirements.txt",
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
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not candidates:
        return [], []

    model = _load_model()
    pairs = [(query_en, item.get("text") or "") for item in candidates]
    scores = model.predict(pairs, show_progress_bar=False)

    scored: list[dict[str, Any]] = []
    for item, rerank_score in zip(candidates, scores, strict=True):
        enriched = dict(item)
        enriched["rerank_score"] = float(rerank_score)
        enriched["embed_score"] = float(item.get("score", 0.0))
        scored.append(enriched)

    scored.sort(key=lambda item: item["rerank_score"], reverse=True)

    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for item in scored:
        if item["rerank_score"] >= min_score and len(kept) < top_k:
            kept.append(item)
        else:
            dropped.append(item)

    return kept, dropped
