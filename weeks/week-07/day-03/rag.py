from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

WORD_RE = re.compile(r"[A-Za-zА-Яа-я0-9_-]{2,}")


@dataclass
class KnowledgeDoc:
    doc_id: str
    title: str
    path: Path
    text: str
    keywords: set[str]


def _tokenize(text: str) -> set[str]:
    return {match.group(0).lower() for match in WORD_RE.finditer(text)}


def _extract_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return fallback


def load_kb(kb_dir: Path) -> list[KnowledgeDoc]:
    docs: list[KnowledgeDoc] = []
    for path in sorted(kb_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8").strip()
        docs.append(
            KnowledgeDoc(
                doc_id=path.stem,
                title=_extract_title(text, path.stem),
                path=path,
                text=text,
                keywords=_tokenize(f"{path.stem} {text}"),
            )
        )
    return docs


def _snippet(text: str, limit: int = 260) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def search_kb(query: str, docs: list[KnowledgeDoc], limit: int = 3) -> dict[str, object]:
    query_terms = _tokenize(query)
    ranked: list[tuple[int, KnowledgeDoc]] = []
    for doc in docs:
        score = len(query_terms & doc.keywords)
        if score > 0:
            ranked.append((score, doc))
    ranked.sort(key=lambda item: (-item[0], item[1].doc_id))
    results = [
        {
            "doc_id": doc.doc_id,
            "title": doc.title,
            "score": score,
            "snippet": _snippet(doc.text),
        }
        for score, doc in ranked[:limit]
    ]
    return {"query": query, "count": len(results), "results": results}
