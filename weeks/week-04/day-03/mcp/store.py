"""SQLite-хранилище задач scheduler MCP."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from croniter import croniter

DAY_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = DAY_DIR / "data" / "scheduler.db"

PROMPT_PREVIEW_CHARS = 80


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _preview(prompt: str) -> str:
    text = prompt.strip()
    if len(text) <= PROMPT_PREVIEW_CHARS:
        return text
    return text[: PROMPT_PREVIEW_CHARS - 1] + "…"


class SchedulerStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                  id            TEXT PRIMARY KEY,
                  kind          TEXT NOT NULL,
                  prompt        TEXT NOT NULL,
                  cron          TEXT,
                  run_at        TEXT,
                  next_run_at   TEXT NOT NULL,
                  last_run_at   TEXT,
                  status        TEXT NOT NULL,
                  run_count     INTEGER DEFAULT 0,
                  created_at    TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_next
                  ON jobs(next_run_at, status);
                """
            )

    def _next_cron_run(self, cron: str, base: datetime) -> datetime:
        iterator = croniter(cron, base)
        nxt = iterator.get_next(datetime)
        if nxt.tzinfo is None:
            return nxt.replace(tzinfo=UTC)
        return nxt.astimezone(UTC)

    def schedule_once(self, delay_seconds: int, prompt: str) -> dict[str, Any]:
        if delay_seconds < 1:
            raise ValueError("delay_seconds must be >= 1")
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("prompt must not be empty")

        now = _now_utc()
        run_at = now + timedelta(seconds=delay_seconds)
        job_id = uuid.uuid4().hex[:12]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                  id, kind, prompt, cron, run_at, next_run_at, status, created_at
                ) VALUES (?, 'once', ?, NULL, ?, ?, 'pending', ?)
                """,
                (job_id, prompt, _iso(run_at), _iso(run_at), _iso(now)),
            )
        return {
            "job_id": job_id,
            "kind": "once",
            "run_at": _iso(run_at),
            "prompt_preview": _preview(prompt),
        }

    def schedule_recurring(self, cron: str, prompt: str) -> dict[str, Any]:
        cron = cron.strip()
        prompt = prompt.strip()
        if not cron:
            raise ValueError("cron must not be empty")
        if not prompt:
            raise ValueError("prompt must not be empty")
        if not croniter.is_valid(cron):
            raise ValueError(f"invalid cron: {cron!r}")

        now = _now_utc()
        next_run_at = self._next_cron_run(cron, now)
        job_id = uuid.uuid4().hex[:12]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                  id, kind, prompt, cron, run_at, next_run_at, status, created_at
                ) VALUES (?, 'recurring', ?, ?, NULL, ?, 'active', ?)
                """,
                (job_id, prompt, cron, _iso(next_run_at), _iso(now)),
            )
        return {
            "job_id": job_id,
            "kind": "recurring",
            "cron": cron,
            "next_run_at": _iso(next_run_at),
            "prompt_preview": _preview(prompt),
        }

    def _stats(self, conn: sqlite3.Connection) -> tuple[int, int, int]:
        pending_total = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status IN ('pending', 'active')"
        ).fetchone()[0]
        active_recurring = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE kind = 'recurring' AND status = 'active'"
        ).fetchone()[0]
        completed_total = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status = 'completed'"
        ).fetchone()[0]
        return int(pending_total), int(active_recurring), int(completed_total)

    def clear_all(self) -> dict[str, Any]:
        with self._connect() as conn:
            deleted = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            conn.execute("DELETE FROM jobs")
        return {"deleted": int(deleted)}

    def _row_to_job_summary(self, row: sqlite3.Row) -> dict[str, Any]:
        item: dict[str, Any] = {
            "id": row["id"],
            "kind": row["kind"],
            "status": row["status"],
            "prompt_preview": _preview(row["prompt"]),
            "next_run_at": row["next_run_at"],
        }
        if row["kind"] == "once" and row["run_at"]:
            item["run_at"] = row["run_at"]
        if row["kind"] == "recurring" and row["cron"]:
            item["cron"] = row["cron"]
        return item

    def list_jobs(self) -> dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, kind, prompt, cron, run_at, next_run_at, status
                FROM jobs
                WHERE status IN ('pending', 'active')
                ORDER BY next_run_at ASC
                """
            ).fetchall()
            jobs = [self._row_to_job_summary(row) for row in rows]
        return {"count": len(jobs), "jobs": jobs}

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        job_id = job_id.strip()
        if not job_id:
            raise ValueError("job_id must not be empty")

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, kind, status, prompt
                FROM jobs
                WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"job not found: {job_id!r}")
            if row["status"] not in ("pending", "active"):
                raise ValueError(
                    f"job {job_id!r} is {row['status']!r}, cannot cancel"
                )
            conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

        return {
            "job_id": job_id,
            "kind": row["kind"],
            "cancelled": True,
            "prompt_preview": _preview(row["prompt"]),
        }

    def check_due(self) -> dict[str, Any]:
        now = _now_utc()
        now_iso = _iso(now)
        due: list[dict[str, Any]] = []

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, kind, prompt, cron, next_run_at, status
                FROM jobs
                WHERE status IN ('pending', 'active') AND next_run_at <= ?
                ORDER BY next_run_at ASC
                """,
                (now_iso,),
            ).fetchall()

            for row in rows:
                job_id = row["id"]
                kind = row["kind"]
                prompt = row["prompt"]
                due.append({"id": job_id, "kind": kind, "prompt": prompt})

                if kind == "once":
                    conn.execute(
                        """
                        UPDATE jobs
                        SET status = 'completed', last_run_at = ?, run_count = run_count + 1
                        WHERE id = ?
                        """,
                        (now_iso, job_id),
                    )
                elif kind == "recurring":
                    cron = row["cron"] or ""
                    next_run_at = self._next_cron_run(cron, now)
                    conn.execute(
                        """
                        UPDATE jobs
                        SET last_run_at = ?, next_run_at = ?, run_count = run_count + 1
                        WHERE id = ?
                        """,
                        (now_iso, _iso(next_run_at), job_id),
                    )

            pending_total, active_recurring, completed_total = self._stats(conn)

        return {
            "checked_at": now_iso,
            "due_count": len(due),
            "due": due,
            "pending_total": pending_total,
            "active_recurring": active_recurring,
            "completed_total": completed_total,
        }
