"""Корпус Gutenberg про опоссумов и сборка изолированных recall-контекстов."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import requests
from agent import DEFAULT_SYSTEM_PROMPT, MODEL_CONTEXT_LIMIT

OPOSSUM_JOKE = (
    "Почему опоссум не играет в прятки? — Потому что когда его находят, "
    "он притворяется мёртвым, а потом всё равно проигрывает: "
    "он ведь не прятался, он «устал»."
)
JOKE_USER_MSG = f"Кстати, анекдот про опоссумов: «{OPOSSUM_JOKE}»"
JOKE_USER_MSG_HARD = f"Ну и шутка про опоссумов: «{OPOSSUM_JOKE}»"
RECALL_QUESTION = "Какой анекдот про опоссумов я писал в самом начале?"
RECALL_QUESTION_HARD = "Какой анекдот про опоссумов я упоминал?"

RECALL_KEYWORDS = ("опоссум", "прятки", "притворяется")
RECALL_KEYWORDS_HARD = ("опоссум", "прятки", "притворяется", "устал")

HARD_JOKE_OFFSET_CHUNKS = 3
HARD_DISTRACTOR_EVERY = 18

HARD_DISTRACTORS = [
    "Кстати, из зоологии: опоссум при опасности притворяется мёртвым — классика.",
    "В детской книжке опоссумы обычно милые ночные зверьки, ничего про игры.",
    "Читал, что опоссумы плохо бегают и редко играют — скорее прячутся в норах.",
    "Забавный факт: опоссум может висеть на хвосте, но в прятки это не считается.",
    "Опоссумы в дикой природе «замирают» при встрече с хищником — похоже на игру, но это нет.",
]

GUTENBERG_BOOKS: list[tuple[str, str]] = [
    ("37199", "Ecology of the Opossum"),
    ("2441", "Burgess Animal Book"),
    ("55704", "Wilderness Babies"),
]

CACHE_DIR = Path(__file__).parent / ".cache"
CORPUS_CACHE = CACHE_DIR / "opossum_corpus.txt"

CHUNK_MIN_CHARS = 1500
CHUNK_MAX_CHARS = 2500
CHARS_PER_TOKEN = 3.5
TOKENS_PER_MESSAGE = 4
# Наблюдённый actual/estimate на EN-корпусе (deepseek) ≈ 0.88–0.90.
ESTIMATE_API_RATIO = 0.88
# Dockhost отклоняет только заметно выше лимита (~+50% estimate); 131711 actual ещё проходит.
OVERFLOW_ACTUAL_MARGIN = 1.35


def overflow_estimate_target() -> int:
    """Цель estimate для overflow: actual prompt_tokens заметно > MODEL_CONTEXT_LIMIT."""
    return int(MODEL_CONTEXT_LIMIT * OVERFLOW_ACTUAL_MARGIN / ESTIMATE_API_RATIO)


@dataclass
class ContextMeta:
    target_pct: int
    hard: bool = False
    books: list[str] = field(default_factory=list)
    corpus_cycles: int = 0
    user_chunks: int = 0
    distractors: int = 0
    estimated_tokens: int = 0
    actual_prompt_tokens: int | None = None


def estimate_tokens(messages: list[dict[str, str]]) -> int:
    total = 0
    for msg in messages:
        total += TOKENS_PER_MESSAGE
        total += int(len(msg.get("content", "")) / CHARS_PER_TOKEN)
    return total


def check_recall(answer: str, *, hard: bool = False) -> bool:
    lower = answer.lower()
    keywords = RECALL_KEYWORDS_HARD if hard else RECALL_KEYWORDS
    return all(keyword in lower for keyword in keywords)


def _gutenberg_urls(book_id: str) -> list[str]:
    return [
        f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.txt",
        f"https://www.gutenberg.org/files/{book_id}/{book_id}-0.txt",
        f"https://www.gutenberg.org/files/{book_id}/{book_id}.txt",
    ]


def _download_book(book_id: str, title: str) -> str:
    last_error: Exception | None = None
    text = ""
    for url in _gutenberg_urls(book_id):
        try:
            response = requests.get(url, timeout=120)
            response.raise_for_status()
            text = response.text
            break
        except requests.RequestException as exc:
            last_error = exc
    if not text:
        raise RuntimeError(f"Не удалось скачать PG#{book_id}: {last_error}") from last_error
    marker = "*** END OF"
    end = text.find(marker)
    if end != -1:
        text = text[:end]
    return f"\n\n=== {title} (PG#{book_id}) ===\n\n{text.strip()}"


def load_corpus_text() -> str:
    if CORPUS_CACHE.exists():
        return CORPUS_CACHE.read_text(encoding="utf-8")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    parts: list[str] = []
    for book_id, title in GUTENBERG_BOOKS:
        print(f"[corpus] скачиваю PG#{book_id} {title}…")
        parts.append(_download_book(book_id, title))
    corpus = "\n".join(parts)
    CORPUS_CACHE.write_text(corpus, encoding="utf-8")
    print(f"[corpus] сохранено в {CORPUS_CACHE.name} ({len(corpus)} символов)")
    return corpus


def _split_corpus(text: str) -> list[tuple[str, str, str]]:
    """Возвращает (book_id, title, chunk_text)."""
    sections = re.split(r"=== (.+?) \(PG#(\d+)\) ===", text)
    chunks: list[tuple[str, str, str]] = []
    if len(sections) < 3:
        for piece in _split_paragraphs(text):
            chunks.append(("?", "corpus", piece))
        return chunks

    i = 1
    while i + 2 < len(sections):
        title = sections[i].strip()
        book_id = sections[i + 1].strip()
        body = sections[i + 2].strip()
        for piece in _split_paragraphs(body):
            chunks.append((book_id, title, piece))
        i += 3
    return chunks


def _split_paragraphs(text: str) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buffer = ""
    for para in paragraphs:
        candidate = f"{buffer}\n\n{para}".strip() if buffer else para
        if len(candidate) > CHUNK_MAX_CHARS and buffer:
            chunks.append(buffer)
            buffer = para
        elif len(candidate) >= CHUNK_MIN_CHARS:
            chunks.append(candidate)
            buffer = ""
        else:
            buffer = candidate
    if buffer:
        chunks.append(buffer)
    return chunks


def _book_usage_label(
    book_id: str,
    title: str,
    used_chars: int,
    total_chars: int,
) -> str:
    if used_chars >= total_chars:
        return f"PG#{book_id} {title} (целиком)"
    pct = int(used_chars / total_chars * 100) if total_chars else 0
    return f"PG#{book_id} {title} (фрагмент {pct}%)"


def _append_book_chunk(
    messages: list[dict[str, str]],
    chunks: list[tuple[str, str, str]],
    chunk_index: int,
    cycles: int,
    meta: ContextMeta,
    book_used: dict[str, int],
) -> int:
    book_id, title, chunk_text = chunks[chunk_index]
    cycle_note = f", цикл {cycles + 1}" if cycles else ""
    header = f"Фрагмент из {title} (PG#{book_id}{cycle_note}):\n\n"
    messages.append({"role": "user", "content": header + chunk_text})
    meta.user_chunks += 1
    book_used[book_id] = book_used.get(book_id, 0) + len(chunk_text)
    return chunk_index + 1


def build_recall_messages(
    fill_pct: int,
    *,
    hard: bool = False,
) -> tuple[list[dict[str, str]], ContextMeta]:
    corpus = load_corpus_text()
    chunks = _split_corpus(corpus)
    if not chunks:
        raise RuntimeError("Корпус пуст — нечем набивать контекст.")

    book_totals: dict[str, int] = {}
    book_used: dict[str, int] = {}
    for book_id, _title, chunk in chunks:
        book_totals[book_id] = book_totals.get(book_id, 0) + len(chunk)

    target_tokens = int(MODEL_CONTEXT_LIMIT * fill_pct / 100)
    messages: list[dict[str, str]] = [{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}]
    meta = ContextMeta(target_pct=fill_pct, hard=hard)
    chunk_index = 0
    cycles = 0
    distractor_idx = 0
    joke_inserted = False

    if hard:
        for _ in range(HARD_JOKE_OFFSET_CHUNKS):
            if chunk_index >= len(chunks):
                cycles += 1
                chunk_index = 0
            chunk_index = _append_book_chunk(
                messages, chunks, chunk_index, cycles, meta, book_used
            )
        messages.append({"role": "user", "content": JOKE_USER_MSG_HARD})
        joke_inserted = True
    else:
        messages.append({"role": "user", "content": JOKE_USER_MSG})
        joke_inserted = True

    while estimate_tokens(messages) < target_tokens:
        if chunk_index >= len(chunks):
            cycles += 1
            chunk_index = 0
        chunk_index = _append_book_chunk(
            messages, chunks, chunk_index, cycles, meta, book_used
        )

        if (
            hard
            and joke_inserted
            and meta.user_chunks % HARD_DISTRACTOR_EVERY == 0
            and distractor_idx < len(HARD_DISTRACTORS)
        ):
            messages.append({"role": "user", "content": HARD_DISTRACTORS[distractor_idx]})
            meta.distractors += 1
            distractor_idx += 1

        if cycles > 20:
            break

    recall_question = RECALL_QUESTION_HARD if hard else RECALL_QUESTION
    messages.append({"role": "user", "content": recall_question})

    meta.corpus_cycles = cycles + 1 if meta.user_chunks else 0
    meta.estimated_tokens = estimate_tokens(messages)

    seen_books: set[str] = set()
    for book_id, title, _ in chunks:
        if book_id in seen_books or book_id not in book_used:
            continue
        seen_books.add(book_id)
        meta.books.append(
            _book_usage_label(book_id, title, book_used[book_id], book_totals[book_id])
        )

    return messages, meta


def build_overflow_messages() -> tuple[list[dict[str, str]], ContextMeta]:
    corpus = load_corpus_text()
    chunks = _split_corpus(corpus)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
        {"role": "user", "content": JOKE_USER_MSG},
    ]

    meta = ContextMeta(target_pct=100)
    chunk_index = 0
    cycles = 0
    target_estimate = overflow_estimate_target()

    while estimate_tokens(messages) < target_estimate:
        if chunk_index >= len(chunks):
            cycles += 1
            chunk_index = 0
        book_id, title, chunk_text = chunks[chunk_index]
        cycle_note = f", цикл {cycles + 1}" if cycles else ""
        header = f"Фрагмент из {title} (PG#{book_id}{cycle_note}):\n\n"
        messages.append({"role": "user", "content": header + chunk_text})
        meta.user_chunks += 1
        chunk_index += 1
        if cycles > 50:
            break

    messages.append({"role": "user", "content": RECALL_QUESTION})
    meta.corpus_cycles = max(cycles + 1, 1)
    meta.estimated_tokens = estimate_tokens(messages)
    meta.books = [
        f"корпус × {meta.corpus_cycles} циклов; "
        f"цель estimate {target_estimate} (лимит API {MODEL_CONTEXT_LIMIT})"
    ]
    return messages, meta


def print_hard_recall_briefing(percentages: list[int]) -> None:
    print("=== СЦЕНАРИЙ (hard recall) ===")
    print(f"[setup] system: «{DEFAULT_SYSTEM_PROMPT}»")
    print("[setup] порядок user-сообщений на каждом шаге:")
    print(f"  1. {HARD_JOKE_OFFSET_CHUNKS} фрагмента книг (Gutenberg, EN)")
    print(f"  2. анекдот: «{JOKE_USER_MSG_HARD}»")
    print("  3. ещё фрагменты книг до целевого % окна")
    print(f"  4. каждые {HARD_DISTRACTOR_EVERY} фрагментов — русский distractor про опоссумов")
    print(f"  5. вопрос recall: «{RECALL_QUESTION_HARD}»")
    print(f"[setup] эталонный анекдот: «{OPOSSUM_JOKE}»")
    print(f"[setup] проверка recall (ключевые слова): {', '.join(RECALL_KEYWORDS_HARD)}")
    print("[setup] distractor-ы (контрольные, примеры):")
    for i, distractor in enumerate(HARD_DISTRACTORS, start=1):
        print(f"  {i}. «{distractor}»")
    books = ", ".join(f"PG#{bid} {title}" for bid, title in GUTENBERG_BOOKS)
    print(f"[setup] корпус книг: {books}")
    print(f"[setup] sweep: {percentages}% — изолированный прогон на каждый %")
    print("[setup] один LLM-вызов на шаг — только на финальный вопрос")
    print()


def print_overflow_briefing() -> None:
    print("=== СЦЕНАРИЙ (overflow) ===")
    print(f"[setup] system: «{DEFAULT_SYSTEM_PROMPT}»")
    print("[setup] порядок: анекдот → книги, пока контекст не превысит лимит → вопрос recall")
    print(f"[setup] анекдот (1-е user-сообщение): «{JOKE_USER_MSG}»")
    print(f"[setup] финальный вопрос: «{RECALL_QUESTION}»")
    print(f"[setup] лимит API (Dockhost): {MODEL_CONTEXT_LIMIT} tok")
    print(
        f"[setup] оценка chars/{CHARS_PER_TOKEN} завышает ~{(1 - ESTIMATE_API_RATIO) * 100:.0f}% — "
        f"для overflow набиваем estimate до {overflow_estimate_target()} tok; "
        f"Dockhost принимает чуть выше {MODEL_CONTEXT_LIMIT}, 400 — при сильном превышении"
    )
    print("[setup] ожидание: HTTP 400 (контекст переполнен)")
    print("[setup] один LLM-вызов; до него история user-only + system")
    books = ", ".join(f"PG#{bid} {title}" for bid, title in GUTENBERG_BOOKS)
    print(f"[setup] корпус: {books}")
    print()


def print_context_meta(meta: ContextMeta) -> None:
    target_tok = int(MODEL_CONTEXT_LIMIT * meta.target_pct / 100)
    print(f"[context] цель: {meta.target_pct}% ({target_tok} / {MODEL_CONTEXT_LIMIT} tok)")
    if meta.hard:
        print(
            f"[context] режим: HARD — анекдот после {HARD_JOKE_OFFSET_CHUNKS} фрагментов книг, "
            f"вопрос без «в начале», {meta.distractors} русских distractor-сообщений"
        )
    else:
        print(
            "[context] режим: standard — анекдот 1-е user-сообщение; "
            "финальный вопрос — единственный recall-промпт"
        )
    if meta.books:
        print(f"[context] загружено user-ом: {', '.join(meta.books)}")
    print(f"[context] {meta.user_chunks} user-фрагментов, корпус × {meta.corpus_cycles} цикла")
    print(f"[context] оценка токенов: {meta.estimated_tokens}")
