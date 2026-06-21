# Week 03, Day 03 — FSM заявки

## Сделано

- `task_state.py`: Stage enum, Artifact (документы), TaskStateStore, linear advance с guard по exit-документу.
- Классификатор: `saves` + `fsm` events; heuristics для pause/resume и ключевых документов (без fixed_message в demo).
- Agent: блок FSM в prompt; отказ skip этапов и смены заявителя.
- Demo: Оскар / Ивановы, 3 сессии (Марта → директор Петровы → Марта), полный проход до `done`.

## Интересное

- Разделение: **документ** (`adoption_application`, `vet_examination_protocol`) vs **событие** (`add_artifact`, `advance`).
- Resume на «чего там с Оскаром?» — не meta-вопрос про FSM.

## Проблемы

- Без heuristics классификатор может промахнуться по документам — добавлен fallback regex.
- user_sim: мета-роль «режиссёр demo» + mode (mistake/recover/conflict) + forbidden в hints.
- Demo длиннее 6–10 ходов (полная машина + конфликты).

## Видео

`python weeks/week-03/day-03/main.py --demo --video` — постранично: clear + переход по любой клавише между ходами.
