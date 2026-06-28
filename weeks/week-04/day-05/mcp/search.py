"""Веб-поиск через ddgs (без API-ключа)."""

from __future__ import annotations

from ddgs import DDGS

SEARCH_TIMEOUT = 15


def search_web(query: str, max_results: int = 5) -> list[dict[str, str]]:
    query = query.strip()
    if not query:
        raise ValueError("query must not be empty")
    max_results = max(1, min(max_results, 10))

    with DDGS(timeout=SEARCH_TIMEOUT) as ddgs:
        raw = ddgs.text(query, max_results=max_results)

    results: list[dict[str, str]] = []
    for item in raw:
        results.append(
            {
                "title": str(item.get("title") or ""),
                "url": str(item.get("href") or item.get("link") or ""),
                "snippet": str(item.get("body") or item.get("snippet") or ""),
            }
        )
    return results
