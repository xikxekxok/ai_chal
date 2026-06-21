"""Три слоя памяти ассистента приюта «Хвостик»."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ADOPTION_CASE_FILE = "adoption_case.json"

DEFAULT_CHARTER = """# Устав ночного приюта «Хвостик»

## Режим работы

Ночная смена: **20:00–06:00**.

## Поведение подопечных

«Игра мёртвой» (dead play) — нормальное поведение опossumов, не повод для паники.

## Карантин и выдача

- Карантин **14 дней** перед усыновлением или передачей в семью.
- Без vet clearance (осмотра доктора Клыка) нельзя обещать выдачу опossuma.
"""


def slugify(name: str) -> str:
    cleaned = name.strip().lower()
    translit = {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
    out = []
    for ch in cleaned:
        if ch in translit:
            out.append(translit[ch])
        elif ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_"):
            out.append("_")
    slug = re.sub(r"_+", "_", "".join(out)).strip("_")
    return slug or "opossum"


@dataclass
class ShortMemory:
    path: Path
    messages: list[dict[str, str]] = field(default_factory=list)

    def load(self) -> None:
        if not self.path.exists():
            self.messages = []
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self.messages = []
            return
        raw = data.get("messages")
        self.messages = [m for m in raw if isinstance(m, dict)] if isinstance(raw, list) else []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"messages": self.messages}
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def add_turn(self, user: str, assistant: str) -> None:
        self.messages.append({"role": "user", "content": user})
        self.messages.append({"role": "assistant", "content": assistant})

    def clear(self) -> None:
        self.messages = []
        self.save()

    def recent(self, limit: int = 8) -> list[dict[str, str]]:
        if limit <= 0:
            return list(self.messages)
        return self.messages[-limit:]

    def stats_line(self) -> str:
        return f"short: {len(self.messages)} сообщений"


@dataclass
class WorkingMemory:
    dir: Path
    opossums: dict[str, dict[str, Any]] = field(default_factory=dict)

    def load(self) -> None:
        self.opossums = {}
        if not self.dir.exists():
            return
        for path in sorted(self.dir.glob("*.json")):
            if path.name == ADOPTION_CASE_FILE:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(data, dict):
                name = str(data.get("name") or path.stem)
                self.opossums[slugify(name)] = data

    def save_opossum(self, slug: str, data: dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / f"{slug}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.opossums[slug] = data

    def update(self, opossum: str, facts: dict[str, Any]) -> list[str]:
        slug = slugify(opossum)
        now = datetime.now(UTC).isoformat()
        record = dict(self.opossums.get(slug, {}))
        record["name"] = opossum.strip()
        record.setdefault("facts", {})
        if not isinstance(record["facts"], dict):
            record["facts"] = {}
        changed: list[str] = []
        for key, value in facts.items():
            if value is None or str(value).strip() == "":
                continue
            key_str = str(key).strip()
            record["facts"][key_str] = str(value).strip()
            changed.append(key_str)
        record["updated_at"] = now
        self.save_opossum(slug, record)
        return changed

    def clear(self) -> None:
        self.opossums = {}
        if self.dir.exists():
            for path in self.dir.glob("*.json"):
                if path.name == ADOPTION_CASE_FILE:
                    continue
                path.unlink()

    def to_prompt_block(self) -> str:
        if not self.opossums:
            return "(рабочая память пуста — нет карточек опossumов)"
        parts: list[str] = []
        for slug in sorted(self.opossums):
            rec = self.opossums[slug]
            name = rec.get("name", slug)
            facts = rec.get("facts") or {}
            lines = [f"### {name}"]
            if isinstance(facts, dict):
                for key, value in sorted(facts.items()):
                    lines.append(f"- {key}: {value}")
            parts.append("\n".join(lines))
        return "\n\n".join(parts)

    def stats_line(self) -> str:
        names = [str(r.get("name", k)) for k, r in self.opossums.items()]
        return f"working: {len(self.opossums)} опossum(ов) [{', '.join(names) or '—'}]"


@dataclass
class LongMemory:
    path: Path
    content: str = ""

    def load(self) -> None:
        if self.path.exists():
            self.content = self.path.read_text(encoding="utf-8")
        else:
            self.content = DEFAULT_CHARTER

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(self.content.rstrip() + "\n", encoding="utf-8")

    def apply_patch(self, patch: str) -> bool:
        text = patch.strip()
        if not text:
            return False
        hours_match = re.search(r"(\d{1,2}:\d{2})\s*[–—-]\s*(\d{1,2}:\d{2})", text)
        if hours_match:
            new_hours = f"{hours_match.group(1)}–{hours_match.group(2)}"
            replaced, count = re.subn(
                r"Ночная смена:\s*\*\*[^*]+\*\*",
                f"Ночная смена: **{new_hours}**",
                self.content,
            )
            if count:
                self.content = replaced
        if text not in self.content:
            stamp = datetime.now(UTC).strftime("%Y-%m-%d")
            block = f"\n\n## Обновление ({stamp})\n\n{text}\n"
            self.content = self.content.rstrip() + block
        self.save()
        return True

    def reset_to_default(self) -> None:
        self.content = DEFAULT_CHARTER
        self.save()

    def to_prompt_block(self) -> str:
        return self.content.strip()

    def stats_line(self) -> str:
        return f"long: charter.md ({len(self.content)} символов)"


@dataclass
class ApplyResult:
    layer: str
    detail: str


@dataclass
class MemoryStore:
    data_dir: Path
    short: ShortMemory = field(init=False)
    working: WorkingMemory = field(init=False)
    long: LongMemory = field(init=False)

    def __post_init__(self) -> None:
        self.short = ShortMemory(self.data_dir / "short" / "dialog.json")
        self.working = WorkingMemory(self.data_dir / "working")
        self.long = LongMemory(self.data_dir / "long" / "charter.md")

    def load(self) -> None:
        self.short.load()
        self.working.load()
        self.long.load()

    def clear_short(self) -> None:
        self.short.clear()

    def clear_working(self) -> None:
        self.working.clear()

    def reset_long(self) -> None:
        self.long.reset_to_default()

    def apply_save(self, item: dict[str, Any]) -> ApplyResult | None:
        layer = str(item.get("layer", "")).strip().lower()
        if layer == "working":
            opossum = str(item.get("opossum", "")).strip()
            facts = item.get("facts")
            if not opossum or not isinstance(facts, dict) or not facts:
                return None
            keys = self.working.update(opossum, facts)
            if not keys:
                return None
            return ApplyResult(layer="working", detail=f"{opossum}: +{', '.join(keys)}")
        if layer == "long":
            patch = str(item.get("patch", "")).strip()
            if not patch:
                return None
            self.long.apply_patch(patch)
            preview = patch[:80] + ("…" if len(patch) > 80 else "")
            return ApplyResult(layer="long", detail=f"charter ← {preview}")
        return None

    def dump_layers(self) -> str:
        lines = [
            "=== short (текущий диалог) ===",
            self.short.stats_line(),
        ]
        if self.short.messages:
            for msg in self.short.messages[-6:]:
                role = "user" if msg["role"] == "user" else "agent"
                content = msg["content"].replace("\n", " ")
                lines.append(f"  [{role}] {content[:120]}{'…' if len(content) > 120 else ''}")
        else:
            lines.append("  (пусто)")

        lines.extend(["", "=== working (опossumы) ===", self.working.stats_line()])
        for slug in sorted(self.working.opossums):
            rec = self.working.opossums[slug]
            facts = rec.get("facts") or {}
            if isinstance(facts, dict):
                for key, value in sorted(facts.items()):
                    lines.append(f"  {rec.get('name', slug)} / {key}: {value}")

        lines.extend(["", "=== long (устав) ===", self.long.stats_line()])
        for line in self.long.content.strip().splitlines()[:12]:
            lines.append(f"  {line}")
        if len(self.long.content.splitlines()) > 12:
            lines.append("  …")
        return "\n".join(lines)

    def context_summary(self) -> str:
        return (
            f"{self.short.stats_line()}\n"
            f"{self.working.stats_line()}\n"
            f"{self.long.stats_line()}\n\n"
            f"Устав (фрагмент):\n{self.long.to_prompt_block()[:600]}\n\n"
            f"Опossumы:\n{self.working.to_prompt_block()}"
        )
