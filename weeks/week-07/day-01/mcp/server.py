"""MCP-сервер: git_branch и list_files (stdio)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

_MCP_DIR = Path(__file__).resolve().parent
DAY_DIR = _MCP_DIR.parent
PROJECT_DIR = DAY_DIR / "project"
REPO_ROOT = DAY_DIR.parents[2]

mcp = FastMCP(
    "project-git",
    instructions="Read-only git and project file listing for a developer assistant.",
)


def _run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "git failed").strip()
        raise RuntimeError(err)
    return result.stdout.strip()


@mcp.tool(description="Return the current git branch of the repository.")
def git_branch() -> dict:
    branch = _run_git("rev-parse", "--abbrev-ref", "HEAD")
    return {"branch": branch, "repo_root": str(REPO_ROOT)}


@mcp.tool(
    description=(
        "List files under the TaskBoard project docs directory "
        "(relative paths). Optional subdirectory under project/."
    )
)
def list_files(subdir: str = "") -> dict:
    root = PROJECT_DIR
    if subdir.strip():
        candidate = (PROJECT_DIR / subdir.strip()).resolve()
        if not str(candidate).startswith(str(PROJECT_DIR.resolve())):
            raise ValueError("subdir escapes project/")
        root = candidate
    if not root.is_dir():
        raise FileNotFoundError(f"not a directory: {root}")
    paths: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            paths.append(path.relative_to(PROJECT_DIR).as_posix())
    return {
        "root": str(PROJECT_DIR),
        "subdir": subdir.strip() or ".",
        "count": len(paths),
        "files": paths,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
