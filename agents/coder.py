"""
coder.py
========
Coder agent — writes and edits files based on Orchestrator instructions.

Model  : MiniMax M2.5 via OpenRouter
Tools  : write_file, edit_file  (write-only)
Returns: list of files created or edited

Rules:
    - Receives instructions from Orchestrator ONLY
    - NEVER reads files for context (Explorer already did that)
    - NEVER runs code or tests (TestRunner does that)
    - Writes exactly what the instruction says — no improvisation
    - Always reports which files were created or changed
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, List

from langchain_core.tools import tool

from agents.base_agent import BaseAgent, TodoList
from core import config
from core.types import AgentName, Task, TaskResult, make_task_result


# ══════════════════════════════════════════════════════════════════════════════
# CODER TOOLS — write-only, no reads allowed
# ══════════════════════════════════════════════════════════════════════════════

@tool
def write_file(path: str, content: str) -> str:
    """
    Create or overwrite a file in the workspace.
    path is relative to the workspace root.
    Creates parent directories automatically.
    Returns a confirmation with the file path and line count.
    """
    workspace = Path(config.WORKSPACE_PATH).resolve()
    target    = (workspace / path).resolve()

    # Block path traversal outside workspace
    if not str(target).startswith(str(workspace)):
        return f"ERROR: path '{path}' is outside the workspace."

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        line_count = content.count("\n") + 1
        return f"OK: wrote {path} ({line_count} lines)"
    except Exception as e:
        return f"ERROR writing '{path}': {e}"


@tool
def edit_file(path: str, old_content: str, new_content: str) -> str:
    """
    Edit an existing file by replacing old_content with new_content.
    path is relative to the workspace root.
    old_content must match exactly what is in the file.
    Returns confirmation or error if the match was not found.
    """
    workspace = Path(config.WORKSPACE_PATH).resolve()
    target    = (workspace / path).resolve()

    if not str(target).startswith(str(workspace)):
        return f"ERROR: path '{path}' is outside the workspace."

    if not target.exists():
        return f"ERROR: file not found: {path}. Use write_file to create it."

    try:
        current = target.read_text(encoding="utf-8")
    except Exception as e:
        return f"ERROR reading '{path}': {e}"

    if old_content not in current:
        # Show a small preview to help the LLM fix its next attempt
        preview = current[:300].replace("\n", "\\n")
        return (
            f"ERROR: old_content not found in '{path}'.\n"
            f"File starts with: {preview}...\n"
            f"Make sure old_content matches the file exactly."
        )

    updated = current.replace(old_content, new_content, 1)

    try:
        target.write_text(updated, encoding="utf-8")
        return f"OK: edited {path}"
    except Exception as e:
        return f"ERROR writing '{path}': {e}"


# ══════════════════════════════════════════════════════════════════════════════
# CODER AGENT
# ══════════════════════════════════════════════════════════════════════════════

class Coder(BaseAgent):
    """
    Coder agent powered by MiniMax M2.5 via OpenRouter.
    Receives precise instructions from the Orchestrator and writes code.

    Override run() to also return the list of files written as artifacts.
    """

    def __init__(self, llm: Any) -> None:
        super().__init__(llm=llm, agent_name=AgentName.CODER)

    # ── system_prompt ─────────────────────────────────────────────────────────

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Coder.\n"
            "\n"
            "YOUR JOB:\n"
            "  Write or edit code files exactly as instructed.\n"
            "  The Orchestrator has already analysed the codebase.\n"
            "  You have everything you need in the instruction.\n"
            "\n"
            "RULES:\n"
            "  - Use write_file to create new files.\n"
            "  - Use edit_file to modify existing files.\n"
            "  - NEVER ask for more context — work with what you have.\n"
            "  - NEVER run code or tests.\n"
            "  - Write complete, working code — no placeholders or TODOs.\n"
            "  - Follow the coding style described in the instruction.\n"
            "\n"
            "WHEN USING edit_file:\n"
            "  old_content must be an exact copy of the lines you want to replace.\n"
            "  Include enough surrounding lines to make it unique in the file.\n"
            "\n"
            "FINAL RESPONSE:\n"
            "  After writing all files, list every file you created or edited:\n"
            "  CHANGES:\n"
            "  - created: path/to/file.py\n"
            "  - edited:  path/to/other.py"
        )

    # ── tools ─────────────────────────────────────────────────────────────────

    @property
    def tools(self) -> List[Any]:
        return [write_file, edit_file]

    # ── build_todos ───────────────────────────────────────────────────────────

    def build_todos(self, task: Task) -> TodoList:
        """
        Parse the instruction to build a file-level todo list.
        Each todo is one file to create or edit.
        """
        todos       = TodoList()
        instruction = task["instruction"].lower()

        # Detect file mentions — lines containing .py .js .ts .go etc
        import re
        file_pattern = re.compile(r'[\w/]+\.\w{1,5}')
        files_mentioned = file_pattern.findall(task["instruction"])

        if files_mentioned:
            seen = set()
            for f in files_mentioned:
                if f not in seen:
                    seen.add(f)
                    action = "edit" if any(w in instruction for w in ["edit", "update", "fix", "change", "modify"]) else "write"
                    todos.add(f"{action} {f}")
        else:
            # No specific files mentioned — generic todos
            if any(w in instruction for w in ["create", "add", "implement", "write", "build"]):
                todos.add("write the required files")
            if any(w in instruction for w in ["edit", "update", "fix", "change", "modify"]):
                todos.add("edit the required files")
            if not todos.items:
                todos.add("implement the requested changes")

        todos.add("confirm all files written in CHANGES: section")

        return todos

    # ── run() override — captures written files as artifacts ──────────────────

    def run(self, task: Task) -> TaskResult:
        """
        Runs the Coder and extracts the list of files written from the output.
        Artifacts are passed to TestRunner via task context.
        """
        result = super().run(task)

        # Parse artifact file paths from the CHANGES: section
        artifacts = self._extract_artifacts(result["output"])

        # Return result with artifacts embedded in output for dispatcher
        return TaskResult(
            task    = result["task"],
            output  = result["output"],
            success = result["success"],
        )

    # ── Private helper ────────────────────────────────────────────────────────

    def _extract_artifacts(self, output: str) -> List[str]:
        """
        Parses the CHANGES: section from Coder output.
        Returns a list of file paths that were created or edited.

        Example output section:
            CHANGES:
            - created: src/auth.py
            - edited:  src/routes.py
        """
        import re
        artifacts = []

        # Find lines like "- created: path" or "- edited: path"
        pattern = re.compile(
            r'-\s+(?:created|edited|wrote|modified|updated):\s*(\S+)',
            re.IGNORECASE
        )
        for match in pattern.finditer(output):
            artifacts.append(match.group(1))

        # Also find any write_file calls by looking at tool output confirmations
        ok_pattern = re.compile(r'OK:\s+wrote\s+(\S+)')
        for match in ok_pattern.finditer(output):
            path = match.group(1)
            if path not in artifacts:
                artifacts.append(path)

        return artifacts