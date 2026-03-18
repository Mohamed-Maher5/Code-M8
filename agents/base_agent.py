
# agents/base_agent.py
# Abstract base class for all agents — ReAct pattern via LangGraph
# Graph: START → llm_node → (tools?) → tool_node → llm_node → END

from __future__ import annotations

import re
import time
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

from core.types import AgentName, Task, TaskResult, make_task_result
from utils.logger import logger


# ── Todo Status ───────────────────────────────────────────────────────────────

class TodoStatus(str, Enum):
    PENDING = "pending"
    DONE    = "done"
    SKIPPED = "skipped"
    FAILED  = "failed"


# ── Todo Item ─────────────────────────────────────────────────────────────────

@dataclass
class TodoItem:
    description: str
    status     : TodoStatus = TodoStatus.PENDING
    result     : str        = ""

    def mark_done(self, result: str = "") -> None:
        self.status = TodoStatus.DONE
        self.result = result[:200]  # cap result length

    def mark_failed(self, reason: str = "") -> None:
        self.status = TodoStatus.FAILED
        self.result = reason[:200]

    def mark_skipped(self, reason: str = "") -> None:
        self.status = TodoStatus.SKIPPED
        self.result = reason[:200]


# ── Todo List ─────────────────────────────────────────────────────────────────

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

    def any_failed(self) -> bool:
        return any(i.status == TodoStatus.FAILED for i in self.items)

    def pending_count(self) -> int:
        return sum(1 for i in self.items if i.status == TodoStatus.PENDING)

    def as_text(self) -> str:
        """Renders the todo list as text for the LLM system prompt."""
        if not self.items:
            return ""
        icons = {
            TodoStatus.PENDING: "[ ]",
            TodoStatus.DONE   : "[x]",
            TodoStatus.SKIPPED: "[-]",
            TodoStatus.FAILED : "[!]",
        }
        lines = ["YOUR TODO LIST — work through these in order:"]
        for i, item in enumerate(self.items, 1):
            icon   = icons[item.status]
            result = f" → {item.result[:80]}" if item.result else ""
            lines.append(f"  {i}. {icon} {item.description}{result}")
        return "\n".join(lines)

    def to_dict(self) -> List[dict]:
        """Serializes todo list for session storage."""
        return [
            {
                "description": item.description,
                "status"     : item.status.value,
                "result"     : item.result,
            }
            for item in self.items
        ]


# ── Agent State ───────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


# ── Tool → Todo keyword map ───────────────────────────────────────────────────
# maps tool names to keywords that identify which todo they satisfy

TOOL_TODO_MAP = {
    "read_file"         : ["read", "verify", "check"],
    "read_file_for_edit": ["read", "verify", "check"],
    "list_files"        : ["list"],
    "search_code"       : ["search", "find"],
    "write_file"        : ["write", "create", "implement", "build", "add"],
    "edit_file"         : ["edit", "modify", "update", "fix", "change"],
}


# ── Base Agent ────────────────────────────────────────────────────────────────

class BaseAgent(ABC):

    def __init__(self, llm: Any, agent_name: AgentName) -> None:
        self.llm        = llm
        self.name       = agent_name
        self._graph     = self._build_graph()
        self._todos     : Optional[TodoList] = None  # active todos for current run
        logger.info(f"BaseAgent [{self.name.value}] initialised")

    # ── Abstract interface ────────────────────────────────────────────────────

    @property
    @abstractmethod
    def system_prompt(self) -> str: ...

    @property
    @abstractmethod
    def tools(self) -> List[Any]: ...

    @abstractmethod
    def build_todos(self, task: Task) -> TodoList: ...

    # ── run() ─────────────────────────────────────────────────────────────────

    def run(self, task: Task) -> TaskResult:
        start_time = time.time()

        # build todos and store on instance so nodes can access them
        self._todos     = self.build_todos(task)
        full_system     = self._build_system_with_todos(self._todos)

        messages: List[BaseMessage] = [SystemMessage(content=full_system)]

        if task.get("context"):
            messages.append(HumanMessage(content=f"Context:\n{task['context']}"))

        messages.append(HumanMessage(content=task["instruction"]))

        output = ""

        for chunk in self._graph.stream({"messages": messages}):
            node_name = list(chunk.keys())[0]
            state     = chunk[node_name]

            if node_name == "llm" and state.get("messages"):
                last_msg = state["messages"][-1]
                if hasattr(last_msg, "content") and last_msg.content:
                    # only capture final text responses — not tool call messages
                    if not getattr(last_msg, "tool_calls", None):
                        output = last_msg.content.strip()
                        print(f"  💬 Agent answered")

                        # parse TODO_DONE: lines from LLM output
                        # and update todo statuses in real time
                        self._parse_todo_updates(output)

            if node_name == "tools" and state.get("messages"):
                for msg in state["messages"]:
                    if isinstance(msg, ToolMessage):
                        # update todo status based on tool result
                        self._update_todo_from_tool(msg)
                        print(f"  🔧 Tool ran: {msg.name}")

        # mark any todos still pending as skipped
        # — agent finished without explicitly completing them
        if self._todos:
            for item in self._todos.items:
                if item.status == TodoStatus.PENDING:
                    item.mark_skipped("agent finished without completing this")

        duration_ms = int((time.time() - start_time) * 1000)
        logger.info(f"BaseAgent [{self.name.value}] done in {duration_ms}ms")

        # log final todo summary to app.log
        self._log_todo_summary()

        # success = output exists AND no todos failed
        success = bool(output) and not (self._todos and self._todos.any_failed())

        return make_task_result(task=task, output=output, success=success)

    # ── LangGraph nodes ───────────────────────────────────────────────────────

    def _llm_node(self, state: AgentState) -> dict:
        msgs  = state["messages"]
        print(f"\n  🧠  Thinking... ({len(msgs)} messages in context)")

        bound    = self.llm.bind_tools(self.tools) if self.tools else self.llm
        response = bound.invoke(msgs)

        if getattr(response, "tool_calls", None):
            for tc in response.tool_calls:
                print(f"  📌 Will call: {tc['name']}")

        return {"messages": [response]}

    def _tool_node(self, state: AgentState) -> dict:
        last     = state["messages"][-1]
        tool_map = {t.name: t for t in self.tools}
        results  = []

        for tc in last.tool_calls:
            tool_fn   = tool_map.get(tc["name"])
            tool_name = tc["name"]
            print(f"\n  ⚙️   Running: {tool_name}({list(tc.get('args', {}).keys())})")

            if tool_fn is None:
                # tool not registered — this is a real error
                output  = f"ERROR: unknown tool '{tool_name}' — not available to this agent"
                success = False
            else:
                try:
                    output  = tool_fn.invoke(tc.get("args", {}))
                    # check if tool returned an error string
                    # tools return "ERROR: ..." strings on failure
                    success = not str(output).startswith("ERROR")
                except Exception as e:
                    output  = f"ERROR: {e}"
                    success = False

            icon = "✅" if success else "❌"
            print(f"  {icon} Done: {tool_name}")

            results.append(ToolMessage(
                content      = str(output),
                tool_call_id = tc["id"],
                name         = tool_name,
            ))

        return {"messages": results}

    # ── Routing ───────────────────────────────────────────────────────────────

    def _should_continue(self, state: AgentState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
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
            END    : END,
        })
        g.add_edge("tools", "llm")

        return g.compile()

    # ── Todo helpers ──────────────────────────────────────────────────────────

    def _build_system_with_todos(self, todos: TodoList) -> str:
        """
        Injects todo list and checklist rules into the system prompt.
        The LLM is instructed to report each todo result using
        a structured TODO_DONE: line so we can parse and update statuses.
        """
        base      = self.system_prompt.strip()
        todo_text = todos.as_text()

        if not todo_text:
            return base

        checklist_instructions = (
            "\n\nCHECKLIST RULES:\n"
            "  - Work through your todo list in order, one item at a time.\n"
            "  - After completing each item report the result using this exact format:\n"
            "    TODO_DONE: <description> | STATUS: passed | RESULT: <what happened>\n"
            "    TODO_DONE: <description> | STATUS: failed | RESULT: <what went wrong>\n"
            "    TODO_DONE: <description> | STATUS: skipped | RESULT: <why skipped>\n"
            "  - Do NOT move to the next item until you have reported the current one.\n"
            "  - If a todo fails, explain why clearly before continuing.\n"
            "  - Your final response must end with a SUMMARY: section listing all statuses.\n"
        )

        return f"{base}\n\n{todo_text}\n{checklist_instructions}"

    def _parse_todo_updates(self, text: str) -> None:
        """
        Parses TODO_DONE: lines from LLM output and updates TodoItem statuses.

        Expected format:
            TODO_DONE: <description> | STATUS: passed/failed/skipped | RESULT: <detail>

        Matches todos by finding the pending item whose description
        has the most word overlap with the reported description.
        """
        if not self._todos:
            return

        pattern = re.compile(
            r"TODO_DONE:\s*(.+?)\s*\|\s*STATUS:\s*(passed|failed|skipped)\s*\|\s*RESULT:\s*(.+)",
            re.IGNORECASE,
        )

        for match in pattern.finditer(text):
            reported_desc = match.group(1).strip().lower()
            status        = match.group(2).strip().lower()
            result        = match.group(3).strip()

            # find the best matching pending todo by word overlap
            best_item  : Optional[TodoItem] = None
            best_score : int                = 0

            reported_words = set(reported_desc.split())

            for item in self._todos.items:
                if item.status != TodoStatus.PENDING:
                    continue  # only match pending items
                item_words = set(item.description.lower().split())
                score      = len(reported_words & item_words)
                if score > best_score:
                    best_score = score
                    best_item  = item

            if best_item and best_score > 0:
                if status == "passed":
                    best_item.mark_done(result)
                elif status == "failed":
                    best_item.mark_failed(result)
                elif status == "skipped":
                    best_item.mark_skipped(result)

                logger.info(
                    f"[{self.name.value}] todo updated: "
                    f"'{best_item.description}' → {status}"
                )

    def _update_todo_from_tool(self, tool_message: ToolMessage) -> None:
        """
        Updates todo status based on tool execution result.
        Called from run() after every tool node execution.

        Logic:
          - tool output starting with ERROR → mark matching todo failed
          - tool output not starting with ERROR → mark matching todo done
          - match is done by finding the first pending todo whose description
            contains a keyword associated with the tool name
        """
        if not self._todos:
            return

        tool_name = getattr(tool_message, "name", "")
        content   = str(getattr(tool_message, "content", ""))
        succeeded = not content.startswith("ERROR")

        keywords = TOOL_TODO_MAP.get(tool_name, [])
        if not keywords:
            return  # unknown tool — do not touch todos

        for item in self._todos.items:
            if item.status != TodoStatus.PENDING:
                continue  # only update pending todos
            item_lower = item.description.lower()
            if any(kw in item_lower for kw in keywords):
                if succeeded:
                    item.mark_done(f"{tool_name} → {content[:100]}")
                else:
                    item.mark_failed(f"{tool_name} → {content[:100]}")
                logger.info(
                    f"[{self.name.value}] todo from tool: "
                    f"'{item.description}' → {'done' if succeeded else 'failed'}"
                )
                break  # one tool call updates one todo — stop after first match

    def _log_todo_summary(self) -> None:
        """
        Logs the final todo summary to app.log after the agent finishes.
        This is what gets stored in the session file for this agent's turn.
        """
        if not self._todos:
            return

        total   = len(self._todos.items)
        done    = sum(1 for i in self._todos.items if i.status == TodoStatus.DONE)
        failed  = sum(1 for i in self._todos.items if i.status == TodoStatus.FAILED)
        skipped = sum(1 for i in self._todos.items if i.status == TodoStatus.SKIPPED)

        logger.info(
            f"[{self.name.value}] todo summary: "
            f"{done}/{total} done · {failed} failed · {skipped} skipped"
        )

        for item in self._todos.items:
            logger.info(
                f"  [{item.status.value:7s}] {item.description}"
                + (f" — {item.result}" if item.result else "")
            )

    # ── repr ──────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(agent={self.name.value!r})"