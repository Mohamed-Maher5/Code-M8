"""
base_agent.py
=============
Abstract base class for all agents.
Follows the ReAct pattern from the reference files.

Graph:
    START → llm_node → (tool calls?) → tool_node → llm_node → END
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Annotated, Any, List, Optional

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from core.types import AgentName, Task, TaskResult, ToolResult, make_task_result


# ══════════════════════════════════════════════════════════════════════════════
# TODO LIST
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
        """Injected into system prompt so the LLM tracks its own progress."""
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
# AGENT STATE  (matches reference files exactly)
# ══════════════════════════════════════════════════════════════════════════════

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


# ══════════════════════════════════════════════════════════════════════════════
# BASE AGENT
# ══════════════════════════════════════════════════════════════════════════════

class BaseAgent(ABC):
    """
    All agents inherit from here.

    Provides the ReAct LangGraph loop:
        START → llm → (tool calls?) → tools → llm → END

    Each subclass must implement:
        system_prompt  — who the agent is and what it does
        tools          — list of LangChain @tool functions it can use
        build_todos()  — what steps it needs for a given task
    """

    def __init__(self, llm: Any, agent_name: AgentName) -> None:
        self.llm   = llm
        self.name  = agent_name
        self._graph = self._build_graph()

    # ── Abstract ──────────────────────────────────────────────────────────────

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        ...

    @property
    @abstractmethod
    def tools(self) -> List[Any]:
        ...

    @abstractmethod
    def build_todos(self, task: Task) -> TodoList:
        ...

    # ── run() — only method dispatcher calls ──────────────────────────────────

    # def run(self, task: Task) -> TaskResult:
    #     """Run the task through the LangGraph and return a TaskResult."""
    #     start_time = time.time()

    #     todos       = self.build_todos(task)
    #     full_system = self._build_system_with_todos(todos)

    #     # Build starting messages
    #     history  = task.get("context", "")
    #     messages: List[BaseMessage] = [SystemMessage(content=full_system)]
    #     if history:
    #         messages.append(HumanMessage(content=f"Context:\n{history}"))
    #     messages.append(HumanMessage(content=task["instruction"]))

    #     # Run the graph
    #     final_state = self._graph.invoke({"messages": messages})

    #     # Extract final text from last AIMessage
    #     output = ""
    #     for msg in reversed(final_state["messages"]):
    #         if isinstance(msg, AIMessage) and isinstance(msg.content, str) and msg.content.strip():
    #             output = msg.content.strip()
    #             break

    #     duration_ms = int((time.time() - start_time) * 1000)

    #     return make_task_result(task=task, output=output, success=True)
    def run(self, task: Task) -> TaskResult:
     start_time = time.time()
     task["status"] = "running"

     todos       = self.build_todos(task)
     full_system = self._build_system_with_todos(todos)

     messages = [SystemMessage(content=full_system)]
     if task.get("context"):
        messages.append(HumanMessage(content=f"Context:\n{task['context']}"))
     messages.append(HumanMessage(content=task["instruction"]))

     output = ""

     # Stream instead of invoke — get state after every node
     for chunk in self._graph.stream({"messages": messages}):

        # chunk is a dict: {"node_name": state_update}
        node_name = list(chunk.keys())[0]
        state     = chunk[node_name]

        # After tool node — a tool just ran, print what happened
        if node_name == "tools" and state.get("messages"):
            last_msg = state["messages"][-1]
            if hasattr(last_msg, "name"):
                print(f"  🔧 Tool ran: {last_msg.name}")

        # After llm node — check if it is the final answer
        if node_name == "llm" and state.get("messages"):
            last_msg = state["messages"][-1]
            if hasattr(last_msg, "content") and last_msg.content:
                if not getattr(last_msg, "tool_calls", None):
                    output = last_msg.content.strip()
                    print(f"  💬 Agent answered")

     duration_ms = int((time.time() - start_time) * 1000)
     return make_task_result(task=task, output=output, success=True)


    











    

    # ── LangGraph nodes ───────────────────────────────────────────────────────

    # def _llm_node(self, state: AgentState) -> dict:
    #     """Calls the LLM. Returns text or tool call request."""
    #     bound = self.llm.bind_tools(self.tools) if self.tools else self.llm
    #     response = bound.invoke(state["messages"])
    #     return {"messages": [response]}

    def _tool_node(self, state: AgentState) -> dict:
     last     = state["messages"][-1]
     tool_map = {t.name: t for t in self.tools}
     results  = []

     for tc in last.tool_calls:
        tool_fn = tool_map.get(tc["name"])

        # Print before
        print(f"\n  ⚙️  Running: {tc['name']}({list(tc.get('args', {}).keys())})")

        if tool_fn is None:
            output  = f"ERROR: unknown tool '{tc['name']}'"
            success = False
        else:
            try:
                output  = tool_fn.invoke(tc.get("args", {}))
                success = True
            except Exception as e:
                output  = f"ERROR: {e}"
                success = False

        # Print result status
        # icon = "✅" if success else "❌"
        # print(f"  {icon} Done: {tc['name']}")
        if success:
             icon = "✅"
             print(f"  {icon} Done: {tc['name']}")
        else:
            icon = "❌"
            print(f"  {icon} fail: {tc['name']}")



        
        results.append(ToolMessage(
            content      = str(output),
            tool_call_id = tc["id"],
            name         = tc["name"],
        ))

     return {"messages": results}



    def _llm_node(self, state: AgentState) -> dict:
     # Show thinking indicator
     msgs = state["messages"]
     print(f"\n  🧠 Thinking... ({len(msgs)} messages in context)")

     bound    = self.llm.bind_tools(self.tools) if self.tools else self.llm
     response = bound.invoke(msgs)

     # If requesting a tool — show what it will do next
     if getattr(response, "tool_calls", None):
        for tc in response.tool_calls:
            print(f"  📌 Will call: {tc['name']}")

     return {"messages": [response]}








    # def _tool_node(self, state: AgentState) -> dict:
    #     """Executes the tool the LLM requested. Returns ToolMessage."""
    #     last     = state["messages"][-1]
    #     tool_map = {t.name: t for t in self.tools}
    #     results: List[ToolMessage] = []

    #     for tc in last.tool_calls:
    #         tool_fn = tool_map.get(tc["name"])
    #         if tool_fn is None:
    #             output = f"ERROR: unknown tool '{tc['name']}'"
    #         else:
    #             try:
    #                 output = tool_fn.invoke(tc.get("args", {}))
    #             except Exception as e:
    #                 output = f"ERROR: {e}"

    #         results.append(ToolMessage(
    #             content      = str(output),
    #             tool_call_id = tc["id"],
    #             name         = tc["name"],
    #         ))

    #     return {"messages": results}

    # ── Routing ───────────────────────────────────────────────────────────────

    def _should_continue(self, state: AgentState) -> str:
        """Tool calls → go to tools. Text response → END."""
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return END

    # ── Graph builder ─────────────────────────────────────────────────────────

    def _build_graph(self) -> Any:
        g = StateGraph(AgentState)
        g.add_node("llm",   self._llm_node)
        g.add_node("tools", self._tool_node)
        g.add_edge(START, "llm")
        g.add_conditional_edges("llm", self._should_continue, {
            "tools": "tools",
            END:     END,
        })
        g.add_edge("tools", "llm")
        return g.compile()

    # ── Helper ────────────────────────────────────────────────────────────────

    def _build_system_with_todos(self, todos: TodoList) -> str:
        base      = self.system_prompt.strip()
        todo_text = todos.as_text()
        if todo_text:
            return f"{base}\n\n{todo_text}"
        return base

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(agent={self.name.value!r})"