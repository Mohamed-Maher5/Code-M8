# tools/write_file.py
# Creates or overwrites a file in the workspace
# Used by: Coder agent

from pathlib import Path

from langchain_core.tools import tool

import core.config as CONFIG


@tool
def write_file(path: str, content: str) -> str:
    """
    Create or overwrite a file in the workspace.
    path is relative to the workspace root.
    Creates parent directories automatically.
    Returns a confirmation with the file path and line count.
    """
    workspace = Path(CONFIG.WORKSPACE_PATH).resolve()
    target    = (workspace / path).resolve()

    if not str(target).startswith(str(workspace)):
        return f"ERROR: path '{path}' is outside the workspace."

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        line_count = content.count("\n") + 1
        return f"OK: wrote {path} ({line_count} lines)"
    except Exception as e:
        return f"ERROR writing '{path}': {e}"