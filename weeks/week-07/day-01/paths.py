"""Пути дня 31."""

from __future__ import annotations

from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
PROJECT_DIR = DAY_DIR / "project"
DATA_DIR = DAY_DIR / "data"
INDEX_PATH = DATA_DIR / "project_index.json"
REPO_ROOT = DAY_DIR.parents[2]
MCP_SERVER = DAY_DIR / "mcp" / "server.py"
