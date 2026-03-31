# tools/read_file.py
# Reads a file from the workspace and returns its content
# Used by: Explorer agent

from pathlib import Path
from fnmatch import fnmatch

from langchain_core.tools import tool

import core.config as CONFIG

def is_blocked_file(path: Path) -> bool:
    """Check if file matches a blocked pattern."""
    name = path.name.lower()
    return any(fnmatch(name, pattern) for pattern in CONFIG.BLOCKED_FILES)


def is_binary_file(path: Path) -> bool:
    """Detect binary files by checking for NULL bytes."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(1024)
            return b"\x00" in chunk
    except Exception:
        return True

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

    # Block sensitive files
    if is_blocked_file(target):
        return f"ERROR: access to '{path}' is blocked."

    # Block binary files
    if is_binary_file(target):
        return f"ERROR: '{path}' appears to be a binary file."
    
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
    
# ------------------------
# Simple test
# ------------------------
if __name__ == "__main__":

    tests = [
        ".env",
        ".env.local",
        "id_rsa",
        "id_rsa.pub",
        "credentials",
        "config.pem",
        "secret.key",
        "api.token",
        "notes.txt",
        "main.py"
    ]

    for t in tests:
        print(t, "->", not is_blocked_file(Path(t)))