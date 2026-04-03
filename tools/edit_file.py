# tools/edit_file.py
# Edits an existing file by replacing old_content with new_content
# Used by: Coder agent

from pathlib import Path

from langchain_core.tools import tool

import core.config as CONFIG


@tool
def edit_file(path: str, old_content: str, new_content: str) -> str:
    """
    Edit an existing file by replacing old_content with new_content.
    path is relative to the workspace root.
    old_content must match exactly what is in the file.
    Returns confirmation or error if the match was not found.
    """
    workspace = Path(CONFIG.WORKSPACE_PATH).resolve()
    target = (workspace / path).resolve()

    if not str(target).startswith(str(workspace)):
        return f"ERROR: path '{path}' is outside the workspace."

    if not target.exists():
        return f"ERROR: file not found: {path}. Use write_file to create it."

    try:
        current = target.read_text(encoding="utf-8")
    except Exception as e:
        return f"ERROR reading '{path}': {e}"

    if old_content not in current:
        preview = current[:300].replace("\n", "\\n")
        return (
            f"ERROR: old_content not found in '{path}'.\n"
            f"File starts with: {preview}...\n"
            f"Make sure old_content matches the file exactly."
        )

    updated = current.replace(old_content, new_content, 1)

    try:
        target.write_text(updated, encoding="utf-8")

        # Track file modification
        try:
            from core.agent_file_tracker import record_file_modified

            record_file_modified(path)
        except ImportError:
            pass

        return f"OK: edited {path}"
    except Exception as e:
        return f"ERROR writing '{path}': {e}"
