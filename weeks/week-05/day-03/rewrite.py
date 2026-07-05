from __future__ import annotations

from console_out import print_tagged
from llm import complete

REWRITE_SYSTEM = (
    "You rewrite a user's question into a single, clear search query for a semantic-search "
    "retrieval system.\n\n"
    "Rules:\n"
    "1. Preserve every proper noun, character name, title, and specific term from the original "
    "question EXACTLY as written. Never replace them with scientific/taxonomic names, "
    "encyclopedic synonyms, or domain jargon.\n"
    "   Bad:  \"Uncle Billy Opossum\" -> \"Virginia opossum (Didelphis virginiana)\"\n"
    "   Bad:  \"play dead\" -> \"exhibit thanatosis\"\n"
    "   Good: keep the original wording, only fix grammar or ambiguity.\n"
    "2. Do not add facts, context, or terminology that isn't already implied by the question.\n"
    "3. If the question refers to earlier chat history, resolve pronouns/references using that "
    "history, but do not add anything else.\n"
    "4. If the question is a single, already-clear question, return it unchanged (just clean "
    "grammar/casing).\n"
    "5. If it contains multiple distinct questions, split into separate self-contained lines.\n"
    "6. Keep the same language as the original question. Never answer the question — output "
    "only the rewritten query, nothing else, one line for a single question."
)


def _normalize_rewrite(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return text.strip()
    if len(lines) == 1:
        return lines[0]
    return " ".join(lines)


def rewrite_query(question_en: str, *, quiet: bool = False) -> str:
    before = question_en.strip()
    result = complete(
        [
            {"role": "system", "content": REWRITE_SYSTEM},
            {
                "role": "user",
                "content": (
                    "Chat history: (none — standalone question)\n\n"
                    f"Question to rewrite:\n{before}"
                ),
            },
        ],
        temperature=0,
    )
    after = _normalize_rewrite(result.strip().strip('"').strip("'"))
    if not quiet:
        print_tagged("rewrite", after)
    return after
