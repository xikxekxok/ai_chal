"""Хранилище инвариантов приюта «Хvостik» — отдельно от диалога."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_INVARIANTS: list[dict[str, str]] = [
    {
        "id": "NO_WATCHKEEPER_PRESCRIBING",
        "title": "Смотритель не назначает лечение",
        "rule": (
            "Смотритель не назначает лечение, не даёт таблетки подопечным и не заказывает "
            "скорую, крематор или иные экстренные меры из‑за dead play. "
            "Медицина — только через доктора Клыка по протоколу."
        ),
    },
    {
        "id": "NO_DOCUMENT_FANTASY",
        "title": "Без фантазийных документов",
        "rule": (
            "Нельзя подписывать, оформлять или «рисовать» документы за других "
            "(ветеринар, директор) или «по ауре», телепатии и т.п. "
            "Документы — только по форме и уполномоченным лицам."
        ),
    },
    {
        "id": "NO_DUMPSTER_FEEDING",
        "title": "Без корма с помойки",
        "rule": (
            "Нельзя кормить подопечных едой с помойки, human junk food или «остатками с бака». "
            "Только рацион по регламенту приюта."
        ),
    },
    {
        "id": "NO_BRIBE_SUBSTITUTION",
        "title": "Без замены этапов взятками",
        "rule": (
            "Пельмени, деньги, «компенсация душой» и прочие подарки не заменяют "
            "этапы усыновления и не закрывают документы."
        ),
    },
    {
        "id": "NO_SOLO_CRITICAL_DECISIONS",
        "title": "Без единоличных критических решений",
        "rule": (
            "Критические решения (отмена регламента, закрытие кейса, смена условий выдачи) "
            "не принимаются одним смотрителем без второй подписи "
            "(директор или ветслужба по типу решения)."
        ),
    },
    {
        "id": "NO_CROSS_SPECIES_THERAPY",
        "title": "Без межвидовой «терапии»",
        "rule": (
            "Нельзя устраивать «терапевтические» контакты подопечных с другими видами "
            "(кот, собака и т.д.) без отдельного протокола."
        ),
    },
    {
        "id": "NO_OPOSSUM_AS_CONTENT",
        "title": "Подопечный не контент",
        "rule": (
            "Нельзя использовать подопечных для PR, стримов, съёмок, костюмов, rave "
            "и прочих медиа-активностей в зонах содержания."
        ),
    },
    {
        "id": "NO_HANDOFF_TO_UNVERIFIED_THIRD",
        "title": "Без передачи посторонним",
        "rule": (
            "Нельзя передать опossuma соседу, таксисту, «другу семьи» и другим лицам "
            "вне заявителя по активному кейсу."
        ),
    },
    {
        "id": "NO_EMOTIONAL_EMERGENCY_RELEASE",
        "title": "Без «экстренной выдачи по жалости»",
        "rule": (
            "Нет «экстренной выдачи» или открытия ворот «потому что семья плачет» — "
            "сочувствие не отменяет регламент; документы и этапы обязательны."
        ),
    },
]


@dataclass
class Invariant:
    id: str
    title: str
    rule: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Invariant | None:
        inv_id = str(data.get("id", "")).strip()
        if not inv_id:
            return None
        return cls(
            id=inv_id,
            title=str(data.get("title", inv_id)).strip(),
            rule=str(data.get("rule", "")).strip(),
        )


@dataclass
class InvariantStore:
    path: Path
    items: list[Invariant] = field(default_factory=list)

    def load(self) -> None:
        if not self.path.exists():
            self.reset_to_seed()
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self.reset_to_seed()
            return
        raw = data.get("invariants") if isinstance(data, dict) else None
        if not isinstance(raw, list):
            self.reset_to_seed()
            return
        items: list[Invariant] = []
        for entry in raw:
            if isinstance(entry, dict):
                inv = Invariant.from_dict(entry)
                if inv:
                    items.append(inv)
        self.items = items or [inv for d in DEFAULT_INVARIANTS if (inv := Invariant.from_dict(d))]

    def reset_to_seed(self) -> None:
        self.items = [inv for d in DEFAULT_INVARIANTS if (inv := Invariant.from_dict(d))]
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "invariants": [{"id": i.id, "title": i.title, "rule": i.rule} for i in self.items]
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def to_prompt_block(self) -> str:
        if not self.items:
            return "(инварианты не загружены)"
        lines = [
            "При конфликте запроса с правилом — откажи, назови **id** инварианта, "
            "предложи легальную альтернативу. Не высмеивай собеседника.",
            "",
        ]
        for inv in self.items:
            lines.append(f"- **{inv.id}** ({inv.title}): {inv.rule}")
        return "\n".join(lines)

    def to_validator_block(self) -> str:
        if not self.items:
            return "(нет инвариантов)"
        lines = []
        for inv in self.items:
            lines.append(f"- {inv.id}: {inv.rule}")
        return "\n".join(lines)

    def dump_section(self) -> str:
        lines = ["=== invariants (long) ===", f"  count={len(self.items)}"]
        for inv in self.items:
            lines.append(f"  {inv.id}: {inv.title}")
        return "\n".join(lines)

    def stats_line(self) -> str:
        return f"invariants: {len(self.items)} правил"
