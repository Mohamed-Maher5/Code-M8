

"""
base_agent.py
=============
Abstract base class for all agents.

Internals use deepagents create_deep_agent + FilesystemBackend.
The external interface is identical — dispatcher.py only calls .run(task).

Each subclass defines:
    system_prompt  — who the agent is and what rules it follows
    tools          — list of LangChain @tool functions
    build_todos()  — step list for a given task (injected into system prompt)
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

from core.config import WORKSPACE_PATH
from core.types import Task, TaskResult, make_task_result


# ══════════════════════════════════════════════════════════════════════════════
# TODO LIST
# Injected into system_prompt so deepagents tracks steps via write_todos tool
# ══════════════════════════════════════════════════════════════════════════════

class TodoStatus(str, Enum):
    PENDING = "pending"
    DONE    = "done"
    SKIPPED = "skipped"
    FAILED  = "failed"


@dataclass
class TodoItem:
    description: str
    status:      TodoStatus = TodoStatus.PENDING
    result:      str        = ""
    todo_id:     str        = field(default_factory=lambda: uuid.uuid4().hex[:6])

    def mark_done(self, result: str = "") -> None:
        self.status = TodoStatus.DONE
        self.result = result

    def mark_failed(self, reason: str = "") -> None:
        self.status = TodoStatus.FAILED
        self.result = reason

    def mark_skipped(self) -> None:
        self.status = TodoStatus.SKIPPED


@dataclass
class TodoList:
    items: List[TodoItem] = field(default_factory=list)

    def add(self, description: str) -> TodoItem:
        item = TodoItem(description=description)
        self.items.append(item)
        return item

    def all_done(self) -> bool:
        return all(
            i.status in (TodoStatus.DONE, TodoStatus.SKIPPED)
            for i in self.items
        )

    def pending_count(self) -> int:
        return sum(1 for i in self.items if i.status == TodoStatus.PENDING)

    def as_text(self) -> str:
        """Injected into system prompt so the agent tracks its own progress."""
        if not self.items:
            return ""
        icons = {
            TodoStatus.PENDING: "[ ]",
            TodoStatus.DONE:    "[x]",
            TodoStatus.SKIPPED: "[-]",
            TodoStatus.FAILED:  "[!]",
        }
        lines = ["Your todo list:"]
        for item in self.items:
            lines.append(f"  {icons[item.status]} {item.description}")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# BASE AGENT
# ══════════════════════════════════════════════════════════════════════════════

class BaseAgent(ABC):
    """
    All agents (Explorer, Coder, Orchestrator) inherit from here.

    Internally uses deepagents create_deep_agent with FilesystemBackend.
    FilesystemBackend confines all file I/O to WORKSPACE_PATH automatically.

    External interface is unchanged:
        agent.run(task) → TaskResult
    Dispatcher never knows what is underneath.
    """

    def __init__(self, llm: Any, agent_name: Any = None) -> None:
        self.llm      = llm
        self.name     = agent_name
        self._backend = FilesystemBackend(
            root_dir     = WORKSPACE_PATH,
            virtual_mode = True,   # blocks path traversal outside workspace
        )
        # Graph is built lazily on first run() call
        # because tools and system_prompt are abstract (not available yet at init)
        self._graph = None

    # ── Abstract — subclasses MUST implement these ────────────────────────────

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """The agent's identity and rules."""
        ...

    @property
    @abstractmethod
    def tools(self) -> List[Any]:
        """LangChain @tool functions this agent can use."""
        ...

    @abstractmethod
    def build_todos(self, task: Task) -> TodoList:
        """Step list for this task — injected into system prompt."""
        ...

    # ── run() — only method dispatcher.py ever calls ──────────────────────────

    def run(self, task: Task) -> TaskResult:
        """
        Execute a task and return a TaskResult.
        Builds the deepagents graph on first call (lazy init).
        """
        start_time = time.time()

        # Build the deepagents graph if not built yet
        if self._graph is None:
            self._graph = self._build_graph()

        # Build todos and inject into system prompt
        todos       = self.build_todos(task)
        full_system = self._build_system_with_todos(todos)

        # Build starting messages
        messages = [SystemMessage(content=full_system)]
        if task.get("context"):
            messages.append(HumanMessage(content=f"Context:\n{task['context']}"))
        messages.append(HumanMessage(content=task["instruction"]))

        output = ""

        # Stream the graph — print live tool calls and thinking
        for chunk in self._graph.stream(
            {"messages": messages},
            config      = {"configurable": {"thread_id": uuid.uuid4().hex}},
            stream_mode = "values",
        ):
            msgs = chunk.get("messages", [])
            if not msgs:
                continue

            last_msg = msgs[-1]

            # Tool call about to run
            if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                for tc in last_msg.tool_calls:
                    print(f"\n  📌 Will call: {tc['name']}")

            # Tool result came back
            elif hasattr(last_msg, "tool_call_id"):
                name = getattr(last_msg, "name", "tool")
                print(f"  ✅ Done: {name}")

            # Final text answer
            elif isinstance(last_msg, AIMessage):
                if isinstance(last_msg.content, str) and last_msg.content.strip():
                    if not getattr(last_msg, "tool_calls", None):
                        output = last_msg.content.strip()
                        print(f"  💬 Agent answered")

        return make_task_result(task=task, output=output, success=True)

    # ── Graph builder ─────────────────────────────────────────────────────────

    def _build_graph(self):
        """
        Builds the deepagents graph for this agent.
        Called once on first run() — subclass tools and system_prompt
        are available by then.

        deepagents automatically provides:
            write_todos  — manages the todo list
            ls, read_file, write_file, edit_file, glob, grep — file ops
            execute      — shell commands (via FilesystemBackend)
        Plus any extra tools from self.tools.
        """
        return create_deep_agent(
            model         = self.llm,
            tools         = self.tools,
            system_prompt = self.system_prompt,
            backend       = self._backend,
        )

    # ── Helper ────────────────────────────────────────────────────────────────

    def _build_system_with_todos(self, todos: TodoList) -> str:
        """Appends the todo list to the system prompt."""
        base      = self.system_prompt.strip()
        todo_text = todos.as_text()
        if todo_text:
            return f"{base}\n\n{todo_text}"
        return base

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(llm={self.llm.__class__.__name__!r})"