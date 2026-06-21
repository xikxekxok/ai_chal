# Неделя 3, день 3 — Task State Machine «Хвостик»

## Задание

Формализованное состояние заявки на выдачу опossuma:

| Поле | Назначение |
|------|------------|
| **stage** | этап процесса (FSM) |
| **step** | текущая работа на этапе |
| **expected_action** | кто что делает дальше |
| **artifacts** | документы-результаты этапов |

Канон стадий: `application_review → home_visit → trial_period → vet_clearance → contract → done`.

## Запуск

**Для записи видео** (постранично, переход по любой клавише):

```bash
source .venv/bin/activate
python weeks/week-03/day-03/main.py --demo --video
```

Обычный прогон:

```bash
python weeks/week-03/day-03/main.py --demo
python weeks/week-03/day-03/main.py --demo --no-stream --video
```

Demo — выдача **Оскара** семье **Ивановых**, 3 сессии (~13 ходов):

1. **Марта** — анкета, ошибочный skip этапа, домашний визит, пауза.
2. **Директор** — попытка отдать Оскара семье Петровых → отказ агента.
3. **Марта** — «чего там с Оскаром?», trial → осмотр → договор → `done`.

`--video`: один ход на экран, снизу «ожидаем переход…», clear по клавише; без финального memory dump.

```bash
python weeks/week-03/day-03/main.py --chat
python weeks/week-03/day-03/main.py --show-memory
python weeks/week-03/day-03/main.py --clear working
```

## Документы по этапам

| Этап | Exit-документ (`type`) |
|------|------------------------|
| `application_review` | `adoption_application` |
| `home_visit` | `home_visit_act` |
| `trial_period` | `trial_period_report` |
| `vet_clearance` | `vet_examination_protocol` |
| `contract` | `adoption_contract` |

## На видео

- `--demo --video` — постраничный режим для записи
- `[demo] что происходит` — FSM, план сессий
- `[state]` — этап, документы, переходы
- `[user]` / `[agent]` — полные реплики
- чеклист ✓/✗ в конце

## Статус

- [ ] Код готов
- [ ] Видео записано
- [ ] Ссылка в таблице курса
- [ ] Обновлён [submissions.md](../../../submissions.md)

## Артефакты

| Тип | Ссылка |
|-----|--------|
| Видео | |
| Код | `weeks/week-03/day-03/` |
