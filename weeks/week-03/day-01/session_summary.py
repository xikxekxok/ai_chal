"""Саммари завершённых диалогов для user_sim (память «как у человека»)."""

from __future__ import annotations

from llm import LlmConfig, UsageTracker, complete

SUMMARY_SYSTEM = """\
Сожми диалог смены приюта опossumов в 3–5 коротких предложений —
как человек вспоминает прошлый день: главное помнит, мелочи забывает.
Без дословных цитат. Русский язык.
"""


def _format_transcript(transcript: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for msg in transcript:
        label = "Пользователь" if msg["role"] == "user" else "Ассистент"
        lines.append(f"{label}: {msg['content']}")
    return "\n\n".join(lines)


def summarize_session(
    config: LlmConfig,
    transcript: list[dict[str, str]],
    session_title: str,
    *,
    tracker: UsageTracker | None = None,
) -> str:
    if not transcript:
        return ""
    dialog = _format_transcript(transcript)
    messages = [
        {"role": "system", "content": SUMMARY_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Смена: {session_title}\n\n"
                f"Диалог:\n{dialog}\n\n"
                "Напиши саммари для себя (только текст, без заголовков)."
            ),
        },
    ]
    text, _ = complete(config, messages, tracker=tracker)
    return text.strip()
