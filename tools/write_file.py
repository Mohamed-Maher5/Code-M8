# # tools/write_file.py
# # Creates or overwrites a file in the workspace
# # Used by: Coder agent

# from pathlib import Path

# from langchain_core.tools import tool

# import core.config as CONFIG


# @tool
# def write_file(path: str, content: str) -> str:
#     """
#     Create or overwrite a file in the workspace.
#     path is relative to the workspace root.
#     Creates parent directories automatically.
#     Returns a confirmation with the file path and line count.
#     """
#     workspace = Path(CONFIG.WORKSPACE_PATH).resolve()
#     target    = (workspace / path).resolve()

#     if not str(target).startswith(str(workspace)):
#         return f"ERROR: path '{path}' is outside the workspace."

#     try:
#         target.parent.mkdir(parents=True, exist_ok=True)
#         target.write_text(content, encoding="utf-8")
#         line_count = content.count("\n") + 1
#         return f"OK: wrote {path} ({line_count} lines)"
#     except Exception as e:
#         return f"ERROR writing '{path}': {e}"





# tools/write_file.py
# Creates or overwrites any file type in the workspace
# Used by: Coder agent

from pathlib import Path
from langchain_core.tools import tool
import base64
import core.config as CONFIG

TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".htm", ".css", ".scss",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env",
    ".md", ".txt", ".rst", ".csv", ".xml", ".sql", ".sh", ".bash",
    ".c", ".cpp", ".h", ".java", ".go", ".rs", ".rb", ".php",
    ".gitignore", ".dockerfile", ".makefile", ""
}

@tool
def write_file(path: str, content: str, encoding: str = "utf-8", is_base64: bool = False) -> str:
    """
    Create or overwrite any file type in the workspace.

    Args:
        path      : File path relative to workspace root.
        content   : File content as a string. For binary files, pass base64-encoded content and set is_base64=True.
        encoding  : Text encoding to use (default: utf-8). Ignored for binary files.
        is_base64 : Set True when passing binary content encoded as base64 (e.g. images, PDFs).

    Returns a confirmation with the file path and line/byte count.
    """
    workspace = Path(CONFIG.WORKSPACE_PATH).resolve()
    target    = (workspace / path).resolve()

    if not str(target).startswith(str(workspace)):
        return f"ERROR: path '{path}' is outside the workspace."

    ext = target.suffix.lower()

    try:
        target.parent.mkdir(parents=True, exist_ok=True)

        if is_base64:
            # binary file — decode base64 and write raw bytes
            try:
                raw_bytes = base64.b64decode(content)
            except Exception as e:
                return f"ERROR: failed to decode base64 content: {e}"
            target.write_bytes(raw_bytes)
            return f"OK: wrote {path} ({len(raw_bytes)} bytes, binary)"

        elif ext in TEXT_EXTENSIONS or ext == "":
            # known text file — write with specified encoding
            target.write_text(content, encoding=encoding)
            line_count = content.count("\n") + 1
            return f"OK: wrote {path} ({line_count} lines, {encoding})"

        else:
            # unknown extension — attempt text write, warn the caller
            try:
                target.write_text(content, encoding=encoding)
                line_count = content.count("\n") + 1
                return (
                    f"OK: wrote {path} ({line_count} lines, {encoding}) "
                    f"— WARNING: unknown extension '{ext}', treated as text. "
                    f"If this is a binary file, resend with is_base64=True."
                )
            except Exception as e:
                return (
                    f"ERROR: could not write '{path}' as text: {e}. "
                    f"If this is a binary file, encode it as base64 and set is_base64=True."
                )

    except Exception as e:
        return f"ERROR writing '{path}': {e}"