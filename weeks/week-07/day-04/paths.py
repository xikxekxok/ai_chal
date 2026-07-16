"""Project paths for week 07 day 04."""

from __future__ import annotations

from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
REPO_ROOT = DAY_DIR.parents[3]
SEED_ROOT = DAY_DIR / "sandbox_seed"
WORKSPACE_ROOT = DAY_DIR / "sandbox_workspace"
