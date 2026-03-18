# agents/coder.py
# Coder agent — writes and edits files based on Orchestrator instructions
# Model  : MiniMax M2.5 via OpenRouter
# Rules  :
#     - Receives instructions from Orchestrator ONLY
#     - NEVER reads files for context (Explorer already did that)
#     - NEVER runs code or tests (TestRunner does that)
#     - Writes exactly what the instruction says — no improvisation
#     - Always reports which files were created or changed
#
# NOTE: Tools are defined here ready to use.
# When base_agent tool node is uncommented, return them in tools property.

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, List

from langchain_core.tools import tool

from agents.base_agent import BaseAgent, TodoList
from core import config
from core.types import AgentName, Task, TaskResult


# ── Coder Tools — write-only, no reads allowed ────────────────────────────────

@tool
def write_file(path: str, content: str) -> str:
    """
    Create or overwrite a file in the workspace.
    path is relative to the workspace root.
    Creates parent directories automatically.
    """
    workspace = Path(config.WORKSPACE_PATH).resolve()
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


@tool
def edit_file(path: str, old_content: str, new_content: str) -> str:
    """
    Edit an existing file by replacing old_content with new_content.
    path is relative to the workspace root.
    old_content must match exactly what is in the file.
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


# ── Coder Agent ───────────────────────────────────────────────────────────────

class Coder(BaseAgent):

    def __init__(self, llm: Any) -> None:
        super().__init__(llm=llm, agent_name=AgentName.CODER)

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

    @property
    def tools(self) -> List[Any]:
        return [write_file, edit_file]

    def build_todos(self, task: Task) -> TodoList:
        todos       = TodoList()
        instruction = task["instruction"].lower()

        # detect file mentions in the instruction
        file_pattern    = re.compile(r'[\w/]+\.\w{1,5}')
        files_mentioned = file_pattern.findall(task["instruction"])

        if files_mentioned:
            seen = set()
            for f in files_mentioned:
                if f not in seen:
                    seen.add(f)
                    action = (
                        "edit" if any(
                            w in instruction
                            for w in ["edit", "update", "fix", "change", "modify"]
                        ) else "write"
                    )
                    todos.add(f"{action} {f}")
        else:
            if any(w in instruction for w in ["create", "add", "implement", "write", "build"]):
                todos.add("write the required files")
            if any(w in instruction for w in ["edit", "update", "fix", "change", "modify"]):
                todos.add("edit the required files")
            if not todos.items:
                todos.add("implement the requested changes")

        todos.add("confirm all files written in CHANGES: section")
        return todos

    def run(self, task: Task) -> TaskResult:
        # run base agent then extract artifacts from output
        result    = super().run(task)
        artifacts = self._extract_artifacts(result["output"])
        return TaskResult(
            task   =result["task"],
            output =result["output"],
            success=result["success"],
        )

    def _extract_artifacts(self, output: str) -> List[str]:
        # parses CHANGES: section from Coder output
        # returns list of file paths created or edited
        artifacts = []

        pattern = re.compile(
            r'-\s+(?:created|edited|wrote|modified|updated):\s*(\S+)',
            re.IGNORECASE
        )
        for match in pattern.finditer(output):
            artifacts.append(match.group(1))

        ok_pattern = re.compile(r'OK:\s+wrote\s+(\S+)')
        for match in ok_pattern.finditer(output):
            path = match.group(1)
            if path not in artifacts:
                artifacts.append(path)

        return artifacts