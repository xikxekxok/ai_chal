"""Разбиение текста на чанки с overlap по абзацам/предложениям."""

from __future__ import annotations

import re

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n{2,}")


def chunk_text(
    text: str,
    *,
    size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    if len(cleaned) <= size:
        return [cleaned]

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", cleaned) if p.strip()]
    units: list[str] = []
    for para in paragraphs:
        if len(para) <= size:
            units.append(para)
            continue
        parts = [s.strip() for s in _SENTENCE_SPLIT.split(para) if s.strip()]
        if len(parts) == 1 and len(parts[0]) > size:
            units.extend(_hard_split(parts[0], size))
        else:
            units.extend(parts)

    chunks: list[str] = []
    buf = ""
    for unit in units:
        candidate = f"{buf}\n\n{unit}".strip() if buf else unit
        if len(candidate) <= size:
            buf = candidate
            continue
        if buf:
            chunks.append(buf)
            buf = _overlap_tail(buf, overlap)
            candidate = f"{buf}\n\n{unit}".strip() if buf else unit
        if len(candidate) <= size:
            buf = candidate
        else:
            if buf:
                chunks.append(buf)
            hard = _hard_split(unit, size)
            chunks.extend(hard[:-1])
            buf = hard[-1] if hard else ""
            if buf and overlap and len(buf) > overlap:
                # keep last hard piece as next buffer start
                pass
    if buf:
        chunks.append(buf)

    # merge tiny trailing chunk into previous when sensible
    if len(chunks) >= 2 and len(chunks[-1]) < overlap // 2:
        merged = f"{chunks[-2]}\n\n{chunks[-1]}".strip()
        if len(merged) <= size + overlap:
            chunks = [*chunks[:-2], merged]

    return [c for c in chunks if c.strip()]


def _hard_split(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


def _overlap_tail(text: str, overlap: int) -> str:
    if overlap <= 0 or len(text) <= overlap:
        return text
    tail = text[-overlap:]
    # prefer cutting at whitespace near the start of the tail
    space = tail.find(" ")
    if 0 < space < overlap // 2:
        return tail[space + 1 :]
    return tail
