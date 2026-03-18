# agents/explorer.py
# Explorer agent — reads files and returns findings to the Orchestrator
# Model  : Hunter Alpha via OpenRouter
# Tools  : read_file, list_files, search_code, web_search — imported from tools/

from __future__ import annotations

from typing import Any, List

from agents.base_agent import BaseAgent, TodoList
from core.types import AgentName, Task
from tools.tool_registry import EXPLORER_TOOLS


class Explorer(BaseAgent):

    def __init__(self, llm: Any) -> None:
        super().__init__(llm=llm, agent_name=AgentName.EXPLORER)

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
            "  - You ONLY use read_file, list_files, search_code, and web_search.\n"
            "  - You NEVER write, edit, or create any file.\n"
            "  - You NEVER run code or shell commands.\n"
            "  - Use web_search when the codebase doesn't have enough context\n"
            "    (e.g. how to use a library, find a package, look up an API).\n"
            "  - Your final response is a plain text summary — nothing else.\n"
            "  - Be precise. Include file names, line numbers, and exact "
            "function names when relevant.\n"
            "\n"
            "RESPONSE FORMAT:\n"
            "  End with a clear summary section titled 'FINDINGS:' that "
            "the Orchestrator can read and pass to the Coder."
        )

    @property
    def tools(self) -> List[Any]:
        return EXPLORER_TOOLS

    def build_todos(self, task: Task) -> TodoList:
        todos       = TodoList()
        instruction = task["instruction"].lower()

        todos.add("list workspace files to understand project structure")

        if any(word in instruction for word in ["read", "look at", "check", "open"]):
            todos.add("read the relevant files mentioned in the task")

        if any(word in instruction for word in ["search", "find", "where", "grep", "pattern"]):
            todos.add("search codebase for relevant patterns")

        if any(word in instruction for word in ["how", "library", "package", "api", "docs"]):
            todos.add("search web for relevant documentation if needed")

        todos.add("summarise all findings clearly with FINDINGS: section")

        return todos