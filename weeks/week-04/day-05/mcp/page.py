"""Извлечение основного текста страницы (trafilatura + httpx)."""

from __future__ import annotations

from urllib.parse import urlparse

import httpx
from trafilatura import bare_extraction
from trafilatura.metadata import extract_metadata

MAX_TEXT_CHARS = 4000
FETCH_TIMEOUT = 15.0
MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB
USER_AGENT = "web-search-mcp/1.0 (AI Advent; +https://github.com)"


def _validate_url(url: str) -> str:
    url = url.strip()
    if not url:
        raise ValueError("url must not be empty")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("only http/https URLs are allowed")
    if not parsed.netloc:
        raise ValueError("invalid url")
    return url


def fetch_page(url: str) -> dict[str, object]:
    url = _validate_url(url)
    with httpx.Client(
        timeout=FETCH_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        raw = response.content
        html_truncated = len(raw) > MAX_RESPONSE_BYTES
        if html_truncated:
            raw = raw[:MAX_RESPONSE_BYTES]
        html = raw.decode(response.encoding or "utf-8", errors="replace")

    metadata = extract_metadata(html)
    title = metadata.title if metadata and metadata.title else ""
    extracted = bare_extraction(html, url=url)
    text = (extracted.text or "").strip() if extracted else ""
    if not title and extracted and extracted.as_dict().get("title"):
        title = str(extracted.as_dict()["title"])

    truncated = len(text) > MAX_TEXT_CHARS
    if truncated:
        text = text[:MAX_TEXT_CHARS]

    return {
        "url": url,
        "title": title,
        "chars": len(text),
        "truncated": truncated,
        "html_truncated": html_truncated,
        "text": text,
    }
