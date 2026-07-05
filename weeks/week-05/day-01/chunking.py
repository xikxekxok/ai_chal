from __future__ import annotations

import re
from dataclasses import dataclass

from sources import Book

CHUNK_CHARS = 3200
OVERLAP_CHARS = 320

CHAPTER_RE = re.compile(r"^CHAPTER [IVXLCDM\d]+", re.MULTILINE | re.IGNORECASE)
BURGESS_RE = re.compile(r"^[IVXLCDM]+\.\s+[A-Z]", re.MULTILINE)
MARKDOWN_H_RE = re.compile(r"^### .+", re.MULTILINE)


@dataclass
class ChunkDraft:
    text: str
    meta: dict


def strip_gutenberg_boilerplate(text: str) -> str:
    start = re.search(
        r"\*\*\* START OF (?:THE )?(?:PROJECT )?GUTENBERG.*?\*\*\*",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if start:
        text = text[start.end() :]
    end = re.search(
        r"\*\*\* END OF (?:THE )?(?:PROJECT )?GUTENBERG.*",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if end:
        text = text[: end.start()]
    return text.strip()


def _is_all_caps_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 80:
        return False
    letters = [c for c in stripped if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def build_headings(text: str) -> list[tuple[int, str]]:
    headings: list[tuple[int, str]] = []
    offset = 0
    prev_blank = True
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if not stripped:
            prev_blank = True
            offset += len(line)
            continue

        heading: str | None = None
        if CHAPTER_RE.match(stripped):
            heading = stripped
        elif BURGESS_RE.match(stripped):
            heading = stripped
        elif MARKDOWN_H_RE.match(stripped):
            heading = stripped.removeprefix("### ").strip()
        elif prev_blank and _is_all_caps_heading(stripped):
            heading = stripped

        if heading:
            headings.append((offset, heading))
        prev_blank = False
        offset += len(line)
    return headings


def section_for_offset(headings: list[tuple[int, str]], start_offset: int) -> str:
    current = "intro"
    for offset, title in headings:
        if offset <= start_offset:
            current = title
        else:
            break
    return current


def _find_chunk_end(text: str, start: int, max_end: int) -> int:
    end = min(max_end, len(text))
    if end >= len(text):
        return len(text)
    window = text[start:end]
    split_at = max(window.rfind("\n"), window.rfind(" "))
    if split_at > 0:
        return start + split_at
    return end


def chunk_text(
    text: str,
    book: Book,
    *,
    chunk_chars: int = CHUNK_CHARS,
    overlap_chars: int = OVERLAP_CHARS,
) -> list[ChunkDraft]:
    headings = build_headings(text)
    chunks: list[ChunkDraft] = []
    start = 0
    index = 0

    while start < len(text):
        max_end = start + chunk_chars
        end = _find_chunk_end(text, start, max_end)
        if end <= start:
            end = min(start + chunk_chars, len(text))

        piece = text[start:end].strip()
        if piece:
            chunk_id = f"{book.id}:{index:03d}"
            chunks.append(
                ChunkDraft(
                    text=piece,
                    meta={
                        "chunk_id": chunk_id,
                        "source_id": book.id,
                        "title": book.title,
                        "author": book.author,
                        "section": section_for_offset(headings, start),
                        "char_count": len(piece),
                        "start_offset": start,
                        "end_offset": end,
                    },
                )
            )
            index += 1

        if end >= len(text):
            break
        next_start = max(end - overlap_chars, start + 1)
        if next_start <= start:
            next_start = end
        start = next_start

    return chunks


def chunking_config() -> dict:
    return {
        "strategy": "overlap",
        "chunk_chars": CHUNK_CHARS,
        "overlap_chars": OVERLAP_CHARS,
    }
