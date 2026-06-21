"""Профили пользователей приюта — персонализация ответов ассистента."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SEED_PROFILES: dict[str, dict[str, Any]] = {
    "martha": {
        "id": "martha",
        "name": "Марта",
        "role": "смотритель ночной смены",
        "style": "тёплый, практичный, лёгкий opossum-юмор",
        "format": "пошаговые списки «что сделать сейчас»",
        "constraints": [
            "не паниковать из-за dead play — это норма",
            "нужны конкретные действия на смене",
        ],
        "learned": {},
    },
    "klyk": {
        "id": "klyk",
        "name": "доктор Клык",
        "role": "ночной ветеринар",
        "style": "сухой клинический, без метафор",
        "format": "протокол: наблюдение → оценка → действие; единицы измерения",
        "constraints": [
            "только факты и дозировки",
            "ссылаться на vet clearance из устава",
        ],
        "learned": {},
    },
    "director": {
        "id": "director",
        "name": "директор приюта",
        "role": "руководитель приюта",
        "style": "деловой, авторитетный",
        "format": "executive summary, 2–4 предложения",
        "constraints": [
            "без медицинской жути и графики",
            "фокус на рисках, сроках, соответствии уставу",
        ],
        "learned": {},
    },
}


@dataclass
class UserProfile:
    id: str
    name: str
    role: str
    style: str
    format: str
    constraints: list[str] = field(default_factory=list)
    learned: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserProfile:
        constraints = data.get("constraints") or []
        learned = data.get("learned") or {}
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            role=str(data.get("role", "")),
            style=str(data.get("style", "")),
            format=str(data.get("format", "")),
            constraints=[str(c) for c in constraints] if isinstance(constraints, list) else [],
            learned=(
                {str(k): str(v) for k, v in learned.items()}
                if isinstance(learned, dict)
                else {}
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "style": self.style,
            "format": self.format,
            "constraints": list(self.constraints),
            "learned": dict(self.learned),
        }


@dataclass
class ProfileStore:
    data_dir: Path
    profiles: dict[str, UserProfile] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.dir = self.data_dir / "profiles"

    def load(self) -> None:
        self.profiles = {}
        self.dir.mkdir(parents=True, exist_ok=True)
        for profile_id, seed in SEED_PROFILES.items():
            path = self.dir / f"{profile_id}.json"
            if not path.exists():
                path.write_text(
                    json.dumps(seed, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = deepcopy(seed)
            if isinstance(data, dict):
                self.profiles[profile_id] = UserProfile.from_dict(data)

    def save(self, profile_id: str) -> None:
        profile = self.profiles.get(profile_id)
        if profile is None:
            return
        path = self.dir / f"{profile_id}.json"
        path.write_text(
            json.dumps(profile.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def get(self, profile_id: str) -> UserProfile | None:
        return self.profiles.get(profile_id)

    def all(self) -> list[UserProfile]:
        return [self.profiles[k] for k in sorted(self.profiles)]

    def reset_to_seed(self) -> None:
        for profile_id, seed in SEED_PROFILES.items():
            path = self.dir / f"{profile_id}.json"
            path.write_text(
                json.dumps(deepcopy(seed), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        self.load()

    def apply_update(self, profile_id: str, updates: dict[str, Any]) -> list[str]:
        profile = self.profiles.get(profile_id)
        if profile is None or not updates:
            return []
        learned = updates.get("learned")
        if not isinstance(learned, dict) or not learned:
            return []
        changed: list[str] = []
        for key, value in learned.items():
            key_str = str(key).strip()
            val_str = str(value).strip()
            if not key_str or not val_str:
                continue
            profile.learned[key_str] = val_str
            changed.append(f"{key_str}: {val_str}")
        if changed:
            self.save(profile_id)
        return changed

    def to_prompt_block(self, profile: UserProfile) -> str:
        lines = [
            f"Имя: {profile.name}",
            f"Роль: {profile.role}",
            f"Стиль ответа: {profile.style}",
            f"Формат: {profile.format}",
        ]
        if profile.constraints:
            lines.append("Ограничения:")
            for item in profile.constraints:
                lines.append(f"- {item}")
        if profile.learned:
            lines.append("Уточнения из прошлых диалогов:")
            for key, value in sorted(profile.learned.items()):
                lines.append(f"- {key}: {value}")
        lines.append(
            "Адаптируй тон, длину и структуру ответа под этот профиль. "
            "Не нарушай устав приюта и факты из памяти."
        )
        return "\n".join(lines)

    def format_profile_stdout(self, profile: UserProfile) -> str:
        lines = [
            f"  id: {profile.id}",
            f"  имя: {profile.name} ({profile.role})",
            f"  стиль: {profile.style}",
            f"  формат: {profile.format}",
        ]
        if profile.constraints:
            lines.append(f"  ограничения: {'; '.join(profile.constraints)}")
        if profile.learned:
            learned = ", ".join(f"{k}={v}" for k, v in sorted(profile.learned.items()))
            lines.append(f"  learned: {learned}")
        else:
            lines.append("  learned: (пусто)")
        return "\n".join(lines)

    def dump_section(self) -> str:
        lines = ["=== profiles (персонализация) ===", f"profiles: {len(self.profiles)}"]
        for profile in self.all():
            lines.append(f"  [{profile.id}] {profile.name}")
            lines.append(f"    style: {profile.style}")
            if profile.learned:
                for key, value in sorted(profile.learned.items()):
                    lines.append(f"    learned / {key}: {value}")
            else:
                lines.append("    learned: (пусто)")
        return "\n".join(lines)

    def stats_line(self) -> str:
        learned_count = sum(len(p.learned) for p in self.profiles.values())
        return f"profiles: {len(self.profiles)} пользователей, {learned_count} learned-полей"
