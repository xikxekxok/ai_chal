# Week 04 Day 05 — дело Тофика, orchestration MCP

## Сделано

- Три MCP-сервера: `burrow` (архив) + `trail` (веб) + `snout` (дедукция).
- `MultiMcpClient` маршрутизирует 11 tools; агент `HolmesAgent` с tool-loop.
- Сюжет: пропал шар **Тофика** (week-03 day-05); виновный — Аркадий «Доцент».
- `narration.py` — человекочитаемый текст на каждый tool call.
- `--demo` — один проход (не 4 хода): рассуждения `[holmes]` + полные `[report]`/`[dossier]`/`[clue]`.

- Сюжет усложнён: 4 файла дела, алиби Доцента не в лоб; нужен **trail** (погода Подольск 14.05.2024, вес фитбола).
- `accuse(pete)` только при witness + alibi_broken + shed + weather_confirmed (мин. 4 улики).

## Интересное

- `test_theory` / `accuse` — rule-based дедукция по тегам улик, без LLM в MCP.
- Отсылка к приюту: Марта, Тофик на шаре, TikTok-ролик.
- `--pager`: разрыв после каждого отчёта/улики/реплики; длинные блоки — по высоте терминала.

## Вывод для видео

```bash
python weeks/week-04/day-05/main.py --mcp-test
python weeks/week-04/day-05/main.py --demo --video
```

Показать `[holmes]` → пауза → `[mcp]` + полный блок → … → `[verdict]`. `q` — выход.
