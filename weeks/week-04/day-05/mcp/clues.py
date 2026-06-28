"""Хранилище улик и правила дедукции."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from case import suspect_name

MIN_CLUES_FOR_ACCUSE = 4


def _normalize_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    result: list[str] = []
    for item in tags:
        text = str(item).strip()
        if not text:
            continue
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                for sub in parsed:
                    sub_text = str(sub).strip()
                    if sub_text:
                        result.append(sub_text)
                continue
        result.append(text)
    return result


@dataclass
class ClueStore:
    clues: list[dict[str, Any]] = field(default_factory=list)
    _next_id: int = 1

    def clear(self) -> int:
        count = len(self.clues)
        self.clues.clear()
        self._next_id = 1
        return count

    def add_clue(self, fact: str, source: str, tags: list[str] | None = None) -> dict[str, Any]:
        fact = fact.strip()
        source = source.strip()
        if not fact:
            raise ValueError("fact must not be empty")
        if not source:
            raise ValueError("source must not be empty")
        normalized_tags = _normalize_tags(tags)
        clue = {
            "id": f"clue_{self._next_id}",
            "fact": fact,
            "source": source,
            "tags": normalized_tags,
        }
        self._next_id += 1
        self.clues.append(clue)
        return {"ok": True, "clue": clue, "total": len(self.clues)}

    def list_clues(self) -> dict[str, Any]:
        return {"count": len(self.clues), "clues": list(self.clues)}

    def _all_tags(self) -> set[str]:
        tags: set[str] = set()
        for clue in self.clues:
            for tag in clue.get("tags") or []:
                tags.add(str(tag))
        return tags

    def test_theory(self, suspect_id: str) -> dict[str, Any]:
        suspect_id = suspect_id.strip()
        tags = self._all_tags()
        name = suspect_name(suspect_id)

        if suspect_id == "pete":
            has_witness = "witness_marta" in tags and "near_bushes" in tags
            alibi_broken = "dozent_alibi_broken" in tags
            physical = "shed_traces" in tags or "fiber_theater" in tags
            weather_ok = "weather_confirmed" in tags
            if has_witness and alibi_broken and physical and weather_ok:
                verdict = "supported"
                reason = (
                    "Алиби Доцента рушится журналом беседки; следы и бахрома у сарая; "
                    "метеосводка подтверждает надёжность показаний и следов."
                )
            elif has_witness and alibi_broken and physical:
                verdict = "weak"
                reason = (
                    "Цепочка почти сходится, но показания Марты о штиле и следы "
                    "нужно подкрепить внешней проверкой (тег weather_confirmed)."
                )
            elif has_witness and alibi_broken:
                verdict = "weak"
                reason = "Алиби слабое, но нет материальных улик у сарая/амбара."
            else:
                verdict = "weak"
                reason = (
                    "Мало связок: нужны показания у кустов, срыв алиби у беседки, "
                    "осмотр сарая и метеопроверка."
                )
        elif suspect_id == "crow":
            if "crow_too_heavy" in tags:
                verdict = "busted"
                reason = "Фитбол тяжелее, чем может поднять ворона — версия рушится."
            else:
                verdict = "weak"
                reason = "Клара любит блестящее; проверь вес фитбола через trail."
        elif suspect_id == "sasha":
            if "sasha_alibi" in tags:
                verdict = "busted"
                reason = "Чек лавки в Подольске и свидетели в магазине дают Саше алиби."
            else:
                verdict = "weak"
                reason = "Калитку не запер — но алиби надо подтвердить уликами."
        elif suspect_id == "barbos":
            if "barbos_chained" in tags:
                verdict = "busted"
                reason = "Пёс на цепи; следы у сарая — не собачьи."
            else:
                verdict = "weak"
                reason = "Лай в 18:35 подозрителен, но нет подтверждения, что был свободен."
        else:
            verdict = "busted"
            reason = f"Неизвестный подозреваемый: {suspect_id}"

        return {
            "suspect_id": suspect_id,
            "suspect_name": name,
            "verdict": verdict,
            "reason": reason,
            "clue_count": len(self.clues),
            "tags_seen": sorted(tags),
        }

    def build_timeline(self) -> dict[str, Any]:
        time_clues = [
            c for c in self.clues if any(str(t).startswith("time:") for t in (c.get("tags") or []))
        ]
        time_clues.sort(key=lambda c: _time_sort_key(c.get("tags") or []))
        events = []
        for clue in time_clues:
            time_tag = next((t for t in clue["tags"] if str(t).startswith("time:")), "time:?")
            events.append(
                {
                    "time": time_tag.removeprefix("time:"),
                    "fact": clue.get("fact"),
                    "source": clue.get("source"),
                }
            )
        return {"events": events, "count": len(events)}

    def accuse(self, suspect_id: str) -> dict[str, Any]:
        if len(self.clues) < MIN_CLUES_FOR_ACCUSE:
            return {
                "error": f"нужно минимум {MIN_CLUES_FOR_ACCUSE} улик, сейчас {len(self.clues)}",
            }
        theory = self.test_theory(suspect_id)
        if theory["verdict"] != "supported":
            return {
                "error": (
                    f"теория по {theory['suspect_name']} не подтверждена "
                    f"({theory['verdict']}): {theory['reason']}"
                ),
            }
        return {
            "ok": True,
            "verdict": "guilty",
            "suspect_id": suspect_id,
            "suspect_name": theory["suspect_name"],
            "reason": theory["reason"],
            "clue_count": len(self.clues),
            "victim": "Тофик",
            "case_id": "missing_ball",
        }


def _time_sort_key(tags: list[str]) -> str:
    for tag in tags:
        if str(tag).startswith("time:"):
            return str(tag).removeprefix("time:")
    return "99:99"


_STORE = ClueStore()


def get_store() -> ClueStore:
    return _STORE
