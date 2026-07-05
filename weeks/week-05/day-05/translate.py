from __future__ import annotations

from console_out import print_tagged
from history import Turn
from llm import complete

OPOSSUM_TERMS = (
    "The corpus is about opossums (Virginia possum), not raccoons. "
    "In Russian answers, do not translate possum/opossum as raccoon."
)

TRANSLATE_SYSTEM = (
    "You are a Russian-to-English translator.\n"
    "Translate the user's Russian text into English.\n"
    "Output ONLY the English translation — same kind of sentence as the input.\n"
    "If the input is a question, output one English question.\n"
    "Do NOT answer the question. Do NOT add facts, lists, bullet points, "
    "headings, or explanations.\n"
    "If chat history is provided, resolve pronouns and vague references "
    "(e.g. «their diet», «tell me more») using that history, but do not add "
    "facts beyond what the current message implies.\n"
    "Opossum → opossum or possum in English, never raccoon."
)


def _format_history_block(history: list[Turn]) -> str:
    if not history:
        return "Chat history: (none — standalone message)"
    lines: list[str] = []
    for turn in history:
        label = "User" if turn.role == "user" else "Assistant"
        lines.append(f"{label}: {turn.content}")
    return "Chat history:\n" + "\n".join(lines)


def translate_to_en(text_ru: str, *, history: list[Turn] | None = None) -> str:
    history_block = _format_history_block(history or [])
    result = complete(
        [
            {"role": "system", "content": TRANSLATE_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"{history_block}\n\n"
                    f"Russian text (translate only, do not answer):\n{text_ru}"
                ),
            },
        ],
        temperature=0,
    )
    en = result.strip()
    print_tagged("translate", f"ru→en: {en}")
    return en
