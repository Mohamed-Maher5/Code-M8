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