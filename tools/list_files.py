# tools/list_files.py
# Lists all files and directories inside the workspace
# Used by: Explorer agent

from pathlib import Path
from typing import List

from langchain_core.tools import tool

import core.config as CONFIG


@tool
def list_files(directory: str = ".") -> str:
    """
    List all files and directories inside the workspace.
    directory is relative to the workspace root (default: workspace root).
    Returns a tree-style text representation.
    """
    workspace = Path(CONFIG.WORKSPACE_PATH).resolve()
    target    = (workspace / directory).resolve()

    if not str(target).startswith(str(workspace)):
        return f"ERROR: path '{directory}' is outside the workspace."

    if not target.exists():
        return f"ERROR: directory not found: {directory}"

    lines: List[str] = []

    for item in sorted(target.rglob("*")):
        parts = item.relative_to(workspace).parts
        if any(p in CONFIG.BLOCKED_DIRS for p in parts):
            continue
        rel    = item.relative_to(workspace)
        depth  = len(rel.parts) - 1
        indent = "  " * depth
        icon   = "📁" if item.is_dir() else "📄"
        lines.append(f"{indent}{icon} {item.name}")

    return "\n".join(lines) if lines else f"(directory '{directory}' is empty)"