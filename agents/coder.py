# agents/coder.py
# Coder agent — writes and edits files based on Orchestrator instructions
# Model  : MiniMax M2.5 via OpenRouter
# Tools  : write_file, edit_file — imported from tools/

from __future__ import annotations

import re
from typing import Any, List

from agents.base_agent import BaseAgent, TodoList
from core.types import AgentName, Task, TaskResult
from tools.tool_registry import CODER_TOOLS


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
        "TOOLS YOU HAVE:\n"
        "  - read_file       — read a file before editing it\n"
        "  - write_file      — create a new file or replace entire file content\n"
        "  - edit_file       — replace one specific block inside a file\n"
        "\n"
        "═══════════════════════════════════════════════════\n"
        "CHOOSING THE RIGHT TOOL — read this carefully\n"
        "═══════════════════════════════════════════════════\n"
        "\n"
        "  USE write_file WHEN:\n"
        "    - Creating a new file that does not exist yet\n"
        "    - The task touches more than 3 separate locations in the file\n"
        "    - The task is a whole-file transformation:\n"
        "        removing all comments, reformatting, renaming throughout\n"
        "    - PROCESS:\n"
        "        1. Call read_file to get the full current content\n"
        "        2. Apply ALL changes to the content in your head\n"
        "        3. Call write_file ONCE with the complete new content\n"
        "        4. Call read_file again to verify the result\n"
        "\n"
        "  USE edit_file WHEN:\n"
        "    - Changing ONE specific block or function\n"
        "    - Adding ONE new function or class\n"
        "    - Fixing ONE specific bug\n"
        "    - PROCESS:\n"
        "        1. Call read_file to get the exact current content\n"
        "        2. Copy the exact block verbatim from the file output\n"
        "        3. Call edit_file ONCE with that exact copied block\n"
        "        4. Call read_file again to verify the change landed\n"
        "\n"
        "  NEVER call edit_file more than 3 times on the same file.\n"
        "  If edit_file fails twice — switch to write_file approach.\n"
        "  NEVER guess old_content from memory — always read first.\n"
        "\n"
        "═══════════════════════════════════════════════════\n"
        "VERIFICATION — mandatory after every write or edit\n"
        "═══════════════════════════════════════════════════\n"
        "  After every write_file or edit_file call:\n"
        "    1. Call read_file on the same file\n"
        "    2. Confirm the change is present\n"
        "    3. Confirm nothing else was accidentally removed\n"
        "    4. Only report CHANGES: after verification passes\n"
        "\n"
        "  If verification fails:\n"
        "    - Report exactly what is wrong\n"
        "    - Retry once with corrected content\n"
        "    - If second attempt also fails — report failure clearly\n"
        "\n"
        "RULES:\n"
        "  - NEVER ask for more context\n"
        "  - NEVER run code or tests\n"
        "  - Write complete working code — no placeholders or TODOs\n"
        "  - Follow the coding style in the instruction exactly\n"
        "\n"
        "FINAL RESPONSE:\n"
        "  CHANGES:\n"
        "  - created: path/to/file.py\n"
        "  - edited:  path/to/other.py"
        )

    @property
    def tools(self) -> List[Any]:
        return CODER_TOOLS

    def build_todos(self, task: Task) -> TodoList:
        todos       = TodoList()
        instruction = task["instruction"].lower()

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
        result    = super().run(task)
        artifacts = self._extract_artifacts(result["output"])
        return TaskResult(
            task   =result["task"],
            output =result["output"],
            success=result["success"],
        )

    def _extract_artifacts(self, output: str) -> List[str]:
        artifacts  = []
        pattern    = re.compile(
            r'-\s+(?:created|edited|wrote|modified|updated):\s*(\S+)',
            re.IGNORECASE
        )
        ok_pattern = re.compile(r'OK:\s+wrote\s+(\S+)')

        for match in pattern.finditer(output):
            artifacts.append(match.group(1))

        for match in ok_pattern.finditer(output):
            path = match.group(1)
            if path not in artifacts:
                artifacts.append(path)

        return artifacts