"""Two-stage context pack for ask: note cards → top chunks."""

from __future__ import annotations

from dataclasses import dataclass

from retrieve import ChunkHit, notes_from_hits


@dataclass
class PackedContext:
    cards_text: str
    chunks_text: str
    note_ids: list[int]
    chunk_ids: list[int]
    n_cards: int
    n_chunks: int
    approx_chars: int


def pack_context(
    hits: list[ChunkHit],
    *,
    max_cards: int = 8,
    max_chunks: int = 4,
) -> PackedContext:
    cards = notes_from_hits(hits, limit=max_cards)
    card_lines: list[str] = []
    for c in cards:
        tags = ", ".join(c["tags"]) if c["tags"] else "—"
        summary = (c["summary"] or "").strip() or "(нет summary)"
        card_lines.append(
            f"- note_id={c['id']} | {c['title']}\n  tags: {tags}\n  summary: {summary}"
        )
    cards_text = "\n".join(card_lines) if card_lines else "(нет карточек)"

    chunk_lines: list[str] = []
    chunk_ids: list[int] = []
    for hit in hits[:max_chunks]:
        chunk_ids.append(hit.chunk_id)
        preview = hit.text.strip()
        chunk_lines.append(
            f"### chunk_id={hit.chunk_id} note_id={hit.note_id} "
            f"«{hit.title}» (rrf={hit.rrf_score:.4f})\n{preview}"
        )
    chunks_text = "\n\n".join(chunk_lines) if chunk_lines else "(нет чанков)"

    note_ids = [int(c["id"]) for c in cards]
    approx = len(cards_text) + len(chunks_text)
    return PackedContext(
        cards_text=cards_text,
        chunks_text=chunks_text,
        note_ids=note_ids,
        chunk_ids=chunk_ids,
        n_cards=len(cards),
        n_chunks=len(chunk_ids),
        approx_chars=approx,
    )


def build_ask_messages(question: str, packed: PackedContext) -> list[dict[str, str]]:
    system = (
        "Ты ассистент личного second brain. Отвечай только по переданному контексту. "
        "В ответе: краткое саммари (2–6 предложений), затем явные ссылки на note_id "
        "из контекста. Не выдумывай id заметок, которых нет в контексте. "
        "Если данных мало — скажи об этом."
    )
    user = (
        f"Вопрос: {question}\n\n"
        f"## Stage 1 — карточки заметок\n{packed.cards_text}\n\n"
        f"## Stage 2 — фрагменты (чанки)\n{packed.chunks_text}\n\n"
        "Сформулируй ответ с опорой на эти материалы."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
