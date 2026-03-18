# tools/search_code.py
# Searches for a regex pattern across all code files in the workspace
# Used by: Explorer agent

import re
from pathlib import Path
from typing import List

from langchain_core.tools import tool

import core.config as CONFIG


@tool
def search_code(pattern: str, directory: str = ".") -> str:
    """
    Search for a regex pattern across all code files in the workspace.
    Returns each match with its file path and line number.
    pattern: a Python regex string (e.g. 'def login', 'import auth', 'JWT')
    directory: where to search (default: entire workspace)
    """
    workspace = Path(CONFIG.WORKSPACE_PATH).resolve()
    target    = (workspace / directory).resolve()

    if not str(target).startswith(str(workspace)):
        return f"ERROR: path '{directory}' is outside the workspace."

    try:
        compiled = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return f"ERROR: invalid regex pattern '{pattern}': {e}"

    matches: List[str] = []

    for filepath in sorted(target.rglob("*")):
        parts = filepath.relative_to(workspace).parts
        if any(p in CONFIG.BLOCKED_DIRS for p in parts):
            continue
        if not filepath.is_file():
            continue
        if filepath.stat().st_size / 1024 > CONFIG.MAX_FILE_SIZE_KB:
            continue

        try:
            lines = filepath.read_text(errors="replace").splitlines()
        except Exception:
            continue

        for line_num, line in enumerate(lines, start=1):
            if compiled.search(line):
                rel = filepath.relative_to(workspace)
                matches.append(f"{rel}:{line_num}:  {line.strip()}")

        if len(matches) >= 50:
            matches.append("... (results truncated at 50 matches)")
            break

    if not matches:
        return f"No matches found for pattern '{pattern}' in '{directory}'"

    return "\n".join(matches)