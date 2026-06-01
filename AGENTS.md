# AGENTS.md — AI Advent Challenge #8

## Project overview

Repository for **AI Advent Challenge #8** (35 weekday assignments, 7 weeks × 5 days).  
Stack: **Python 3.11+**. One folder per assignment: `weeks/week-NN/day-DD/`.

Work only in the active day folder unless the user asks to touch other days.

## Setup

```bash
cd /path/to/ai_chall
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Per-day extra dependencies (when needed):

```bash
pip install -r weeks/week-01/day-01/requirements.txt
```

Copy env template: `cp .env.example .env` — never commit `.env`.

## Commands

| Action | Command |
|--------|---------|
| Lint | `ruff check weeks/` |
| Format | `ruff format weeks/` |
| Test | `pytest weeks/ -q` |
| Run day script | `python weeks/week-01/day-01/main.py` (if exists) |

Adjust paths to the active `week-NN/day-DD`.

## Working on a day

1. Open or create files under `weeks/week-NN/day-DD/`.
2. Update that day's `README.md` (goal, status, links).
3. Update root [`submissions.md`](submissions.md) when submitting.
4. Prefer day-local `requirements.txt` for assignment-specific deps.

Submission format (course): **video + code**. Video is primary proof; host video off-repo (Yandex Disk, etc.). Code lives in this GitHub repo.

Assignments drop **14:00 Mon–Fri**. All 5 prior weekdays must be submitted before the next Monday 14:00 or elimination applies.

## Boundaries

- Do **not** commit secrets, `.env`, API keys, or real tokens.
- Do **not** commit large media (`*.mp4`, datasets) — use external storage.
- Do **not** refactor unrelated weeks/days without explicit user request.
- Week **6+** may need VPS or local models — ask before adding infra assumptions.
- Keep changes minimal and scoped to the current assignment.

## Course glossary

| Term | Meaning |
|------|---------|
| **Code-assistant / harness** | Cursor, Codex, Claude Code — tools that write code with you |
| **Agent (in-app)** | LLM called from *your* app/service via API for end users |
| Harness models | Prefer capable models (course suggests trying several) |
| In-app API models | Prefer cost-effective models (e.g. DeepSeek) |

Course culture: cooperative chat, harness-first workflow, demo must work on video.

## Repo layout

```text
weeks/week-01..07/day-01..05/   # assignment code + README
submissions.md                  # local submission tracker
README.md                       # human-facing course notes (Russian)
.cursor/rules/                  # Cursor rules (ai-advent, python)
```
