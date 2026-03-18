# tools/read_file.py
# Reads a file from the workspace and returns its content
# Used by: Explorer agent

from pathlib import Path

from langchain_core.tools import tool

import core.config as CONFIG


@tool
def read_file(path: str) -> str:
    """
    Read a file from the workspace and return its content.
    path is relative to the workspace directory.
    Returns an error string if the file does not exist or is too large.
    """
    workspace = Path(CONFIG.WORKSPACE_PATH).resolve()
    target    = (workspace / path).resolve()

    if not str(target).startswith(str(workspace)):
        return f"ERROR: path '{path}' is outside the workspace."

    if not target.exists():
        return f"ERROR: file not found: {path}"

    if not target.is_file():
        return f"ERROR: '{path}' is a directory, not a file."

    size_kb = target.stat().st_size / 1024
    if size_kb > CONFIG.MAX_FILE_SIZE_KB:
        return (
            f"ERROR: file '{path}' is {size_kb:.0f} KB. "
            f"Max allowed is {CONFIG.MAX_FILE_SIZE_KB} KB."
        )

    try:
        return target.read_text(errors="replace")
    except Exception as e:
        return f"ERROR reading '{path}': {e}"