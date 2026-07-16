"""Local file tools restricted to the sandbox workspace."""

from __future__ import annotations

import difflib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paths import SEED_ROOT, WORKSPACE_ROOT

MAX_PREVIEW_LINES = 40
MAX_FILE_CHARS = 12_000
TEXT_EXTENSIONS = {".md", ".py", ".txt", ".json", ".yaml", ".yml"}


def reset_workspace() -> Path:
    if WORKSPACE_ROOT.exists():
        shutil.rmtree(WORKSPACE_ROOT)
    shutil.copytree(SEED_ROOT, WORKSPACE_ROOT)
    return WORKSPACE_ROOT


def ensure_workspace() -> Path:
    if not WORKSPACE_ROOT.exists():
        reset_workspace()
    return WORKSPACE_ROOT


def _resolve_path(root: Path, relative_path: str) -> Path:
    workspace = root.resolve()
    candidate = (workspace / relative_path).resolve()
    if candidate != workspace and workspace not in candidate.parents:
        raise ValueError(f"path escapes workspace: {relative_path}")
    return candidate


def _read_text_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if len(text) > MAX_FILE_CHARS:
        return text[:MAX_FILE_CHARS] + "\n...<truncated>..."
    return text


def _preview_diff(old_text: str, new_text: str, relative_path: str) -> str:
    diff_lines = list(
        difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
            lineterm="",
        )
    )
    if not diff_lines:
        return "(no changes)"
    if len(diff_lines) > MAX_PREVIEW_LINES:
        clipped = diff_lines[:MAX_PREVIEW_LINES]
        clipped.append("... diff truncated ...")
        diff_lines = clipped
    return "\n".join(diff_lines)


@dataclass(slots=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]

    def as_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools = {
            "list_dir": ToolDefinition(
                name="list_dir",
                description="List files and directories inside the sandbox workspace.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path inside sandbox workspace.",
                            "default": ".",
                        }
                    },
                },
            ),
            "read_file": ToolDefinition(
                name="read_file",
                description="Read a UTF-8 text file from the sandbox workspace.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative file path inside sandbox workspace.",
                        }
                    },
                    "required": ["path"],
                },
            ),
            "search_files": ToolDefinition(
                name="search_files",
                description="Search text files in the sandbox workspace for a substring.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Exact substring to search for.",
                        }
                    },
                    "required": ["query"],
                },
            ),
            "write_file": ToolDefinition(
                name="write_file",
                description=(
                    "Overwrite a text file in the sandbox workspace "
                    "and return diff preview."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative file path inside sandbox workspace.",
                        },
                        "content": {
                            "type": "string",
                            "description": "Full new file content.",
                        },
                    },
                    "required": ["path", "content"],
                },
            ),
        }

    def openai_tools(self) -> list[dict[str, Any]]:
        return [tool.as_openai_tool() for tool in self._tools.values()]

    def has_tool(self, name: str) -> bool:
        return name in self._tools


class ToolExecutor:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or ensure_workspace()).resolve()

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        if name == "list_dir":
            return self._list_dir(arguments.get("path", "."))
        if name == "read_file":
            return self._read_file(arguments["path"])
        if name == "search_files":
            return self._search_files(arguments["query"])
        if name == "write_file":
            return self._write_file(arguments["path"], arguments["content"])
        raise ValueError(f"unknown tool: {name}")

    def _list_dir(self, relative_path: str) -> str:
        path = _resolve_path(self.root, relative_path)
        if not path.exists():
            raise FileNotFoundError(relative_path)
        items = []
        for child in sorted(path.iterdir()):
            kind = "dir" if child.is_dir() else "file"
            items.append({"name": child.name, "type": kind})
        return json.dumps({"path": relative_path, "items": items}, ensure_ascii=False, indent=2)

    def _read_file(self, relative_path: str) -> str:
        path = _resolve_path(self.root, relative_path)
        if not path.is_file():
            raise FileNotFoundError(relative_path)
        return json.dumps(
            {"path": relative_path, "content": _read_text_file(path)},
            ensure_ascii=False,
            indent=2,
        )

    def _search_files(self, query: str) -> str:
        hits: list[dict[str, Any]] = []
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or path.suffix not in TEXT_EXTENSIONS:
                continue
            text = path.read_text(encoding="utf-8")
            for line_no, line in enumerate(text.splitlines(), start=1):
                if query in line:
                    hits.append(
                        {
                            "path": str(path.relative_to(self.root)),
                            "line": line_no,
                            "text": line.strip(),
                        }
                    )
        return json.dumps({"query": query, "matches": hits}, ensure_ascii=False, indent=2)

    def _write_file(self, relative_path: str, content: str) -> str:
        path = _resolve_path(self.root, relative_path)
        old_text = path.read_text(encoding="utf-8") if path.exists() else ""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        preview = _preview_diff(old_text, content, relative_path)
        return json.dumps(
            {
                "path": relative_path,
                "changed": old_text != content,
                "diff_preview": preview,
            },
            ensure_ascii=False,
            indent=2,
        )
