# Неделя 3, день 5 — Контролируемые переходы (TikTok FSM)

## Задание

Явные переходы между стадиями задачи: допустимые состояния, разрешённые переходы, ассистент не «перепрыгивает» этап.

**Модель day-05:** переход делает **волонтёр** (`complete_stage`); FSM ограничивает **ассистента** (не помогает с будущими этапами).

## Demo

**Саша + Тофик на шаре** — волонтёр согласует ролик; попытка skip → `[transition] denied`; resume после паузы.

```bash
source .venv/bin/activate
python weeks/week-03/day-05/main.py --demo --no-stream
```

На видео: `--demo --video --no-stream`

## Что смотреть в stdout

- Вводная с отсылкой к day-04 (Марта и помойка)
- `[classifier] event=update_step | stage_data +story,...`
- `[transition] allowed pitch → welfare_check` — волонтёр закрыл этап
- `[transition] denied …` при skip или неполных фактах
- Resume: тот же кейс, stage не сброшен
- Чеклист переходов в конце

## FSM

```
pitch → welfare_check → rehearsal → publish → done
```

Поля `stage_data` на этап → `complete_stage` от пользователя → код проверяет и advance.

Persist: `data/working/tiktok_shoot.json`, регламент: `data/long/tiktok_regulation.md`

## Статус

- [ ] Код готов
- [ ] Видео записано
- [ ] Ссылка в таблице курса
- [ ] Обновлён [submissions.md](../../../submissions.md)

## Артефакты

| Тип | Ссылка |
|-----|--------|
| Видео | |
| Код | `weeks/week-03/day-05/` |
