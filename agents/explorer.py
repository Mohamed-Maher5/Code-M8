"""
explorer.py
===========
Explorer agent — reads files and returns findings to the Orchestrator.

Rules (enforced by system_prompt):
    - Reads files, searches code, summarises findings
    - NEVER writes or edits any file
    - Returns results to Orchestrator ONLY
    - Never communicates directly with Coder

Tools:
    read_file     — read one file from workspace
    list_files    — list directory tree
    search_code   — grep/regex search across workspace

NOTE:
    Tools are defined here directly.
    When tools/ folder is built, replace with:
        from tools.read_file   import read_file
        from tools.list_files  import list_files
        from tools.search_code import search_code
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, List

from langchain_core.tools import tool

from agents.base_agent import BaseAgent, TodoList
import core.config   as CONFIG
from core.types import AgentName, Task


# ══════════════════════════════════════════════════════════════════════════════
# EXPLORER TOOLS — read-only, no writes allowed
# ══════════════════════════════════════════════════════════════════════════════

@tool
def read_file(path: str) -> str:
    """
    Read a file from the workspace and return its content.
    path is relative to the workspace directory.
    Returns an error string if the file does not exist or is too large.
    """
    workspace = Path(CONFIG.WORKSPACE_PATH).resolve()
    target    = (workspace / path).resolve()

    # Block path traversal outside workspace
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
        # Skip ignored directories
        parts = item.relative_to(workspace).parts
        if any(p in CONFIG.IGNORED_DIRS for p in parts):
            continue
        # Skip ignored extensions
        if item.suffix in CONFIG.IGNORED_EXTENSIONS:
            continue

        rel    = item.relative_to(workspace)
        depth  = len(rel.parts) - 1
        indent = "  " * depth
        icon   = "📁" if item.is_dir() else "📄"
        lines.append(f"{indent}{icon} {item.name}")

    if not lines:
        return f"(directory '{directory}' is empty)"

    return "\n".join(lines)


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
        # Skip ignored dirs and extensions
        parts = filepath.relative_to(workspace).parts
        if any(p in CONFIG.IGNORED_DIRS for p in parts):
            continue
        if filepath.suffix in CONFIG.IGNORED_EXTENSIONS:
            continue
        if not filepath.is_file():
            continue

        # Skip large files
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

        # Cap results to avoid flooding context
        if len(matches) >= 50:
            matches.append("... (results truncated at 50 matches)")
            break

    if not matches:
        return f"No matches found for pattern '{pattern}' in '{directory}'"

    return "\n".join(matches)


# ══════════════════════════════════════════════════════════════════════════════
# EXPLORER AGENT
# ══════════════════════════════════════════════════════════════════════════════

class Explorer(BaseAgent):
    """
    Explorer agent powered by Qwen.
    Reads the codebase and returns a clear summary to the Orchestrator.

    The Orchestrator digests this summary before passing anything to the Coder.
    Explorer never speaks to Coder directly.
    """

    def __init__(self, llm: Any) -> None:
        super().__init__(llm=llm, agent_name=AgentName.EXPLORER)

    # ── system_prompt ─────────────────────────────────────────────────────────

    @property
    def system_prompt(self) -> str:
        return (
            "You are the code Explorer.\n"
            "\n"
            "YOUR JOB:\n"
            "  Read files, search the codebase, and return a clear summary "
            "of your findings to the Orchestrator.\n"
            "\n"
            "RULES:\n"
            "  - You ONLY use read_file, list_files, and search_code.\n"
            "  - You NEVER write, edit, or create any file.\n"
            "  - You NEVER run code or shell commands.\n"
            "  - Your final response is a plain text summary — nothing else.\n"
            "  - Be precise. Include file names, line numbers, and exact "
            "function names when relevant.\n"
            "\n"
            "RESPONSE FORMAT:\n"
            "  End with a clear summary section titled 'FINDINGS:' that "
            "the Orchestrator can read and pass to the Coder."
        )

    # ── tools ─────────────────────────────────────────────────────────────────

    @property
    def tools(self) -> List[Any]:
        return [read_file, list_files, search_code]

    # ── build_todos ───────────────────────────────────────────────────────────

    def build_todos(self, task: Task) -> TodoList:
        """
        Creates a simple step list for any Explorer task.
        The LLM sees this list and works through it step by step.
        """
        todos = TodoList()
        instruction = task["instruction"].lower()

        # Always start with the file tree so the LLM knows what exists
        todos.add("list workspace files to understand project structure")

        # If specific files are mentioned, read them
        if any(word in instruction for word in ["read", "look at", "check", "open"]):
            todos.add("read the relevant files mentioned in the task")

        # If searching for patterns
        if any(word in instruction for word in ["search", "find", "where", "grep", "pattern"]):
            todos.add("search codebase for relevant patterns")

        # Always summarise at the end
        todos.add("summarise all findings clearly with FINDINGS: section")

        return todos