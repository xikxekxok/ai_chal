from __future__ import annotations

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
    "Opossum → opossum or possum in English, never raccoon."
)


def translate_to_en(text_ru: str) -> str:
    result = complete(
        [
            {"role": "system", "content": TRANSLATE_SYSTEM},
            {
                "role": "user",
                "content": f"Russian text (translate only, do not answer):\n{text_ru}",
            },
        ],
        temperature=0,
    )
    return result.strip()
