#!/usr/bin/env python3
"""Download Gutenberg opossum corpus into weeks/week-05/data/raw/."""

from __future__ import annotations

import argparse
import sys

import requests
from chunking import strip_gutenberg_boilerplate
from paths import RAW_DIR
from sources import BOOKS

USER_AGENT = "ai-chall-week5-day01/1.0 (local indexing; +https://github.com)"


def strip_and_save(raw_text: str) -> str:
    return strip_gutenberg_boilerplate(raw_text)


def download_book(book_id: str, url: str) -> str:
    response = requests.get(
        url,
        timeout=60,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    response.encoding = "utf-8"
    return strip_and_save(response.text)


def format_kb(size_bytes: int) -> str:
    return f"{size_bytes // 1024} KB"


def main() -> None:
    parser = argparse.ArgumentParser(description="Download opossum corpus from Project Gutenberg.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if raw file already exists.",
    )
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    total = len(BOOKS)
    total_bytes = 0
    saved_count = 0

    for index, book in enumerate(BOOKS, start=1):
        target = RAW_DIR / book.filename
        if target.exists() and not args.force:
            size = target.stat().st_size
            total_bytes += size
            saved_count += 1
            print(f"[init] skip {book.id} (exists)")
            continue

        print(f"[init] download {index}/{total} {book.id} {book.title}")
        try:
            text = download_book(book.id, book.url)
        except requests.RequestException as exc:
            print(
                f"[error] failed to download {book.id} ({book.title}) from {book.url}: {exc}",
                file=sys.stderr,
            )
            raise SystemExit(1) from exc

        target.write_text(text, encoding="utf-8")
        size = target.stat().st_size
        total_bytes += size
        saved_count += 1
        print(f"[init] saved {book.filename} ({format_kb(size)})")

    rel_raw = RAW_DIR.relative_to(RAW_DIR.parents[1])
    print(
        f"[init] done: {saved_count}/{total} books, "
        f"{total_bytes / (1024 * 1024):.1f} MB total → {rel_raw}/"
    )


if __name__ == "__main__":
    main()
