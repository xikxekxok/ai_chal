# Неделя 3, день 4 — Инварианты и LLM-валидатор

## Задание

Инварианты приюта хранятся **отдельно от диалога** (`data/long/invariants.json`). Ассистент учитывает их в prompt; **LLM-валидатор** проверяет каждый ответ и при нарушении запускает один retry.

## Demo

**«Марта + помойка»** — adversarial user_sim давит, чтобы агент нарушил инвариант. Провал черновика виден как `[agent:invalid]`.

```bash
source .venv/bin/activate
python weeks/week-03/day-04/main.py --demo --no-stream
```

На видео: `--demo --video` (удобно с `--no-stream`).

## Что смотреть в stdout

- `[invariant] at_risk` / `pass` / `✗ draft REJECTED`
- `[agent:invalid]` — ответ, не прошедший валидатор
- `[invariant] retry → pass` — исправление после feedback
- Чеклист: финал по каждому инварианту + «Марта пробила черновик»

## Архитектура хода

```
user → agent (draft) → LLM validator → [retry agent] → short + classifier
```

## Статус

- [x] Код готов
- [ ] Видео записано
- [ ] Ссылка в таблице курса
- [ ] Обновлён [submissions.md](../../../submissions.md)

## Артефакты

| Тип | Ссылка |
|-----|--------|
| Видео | |
| Код | `weeks/week-03/day-04/` |
