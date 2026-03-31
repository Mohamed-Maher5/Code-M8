# agents/base_agent.py
# Abstract base class for all agents — ReAct pattern via LangGraph
# Graph: START → llm_node → (tools?) → tool_node → llm_node → END

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Annotated, Any, List

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
from core.config import AGENT_MESSAGE_BUDGET_TOKENS
from core.token_usage import estimate_tokens
from core.token_usage import record_usage
from ui.interrupt import InterruptError, is_interrupted
from utils.logger import logger


# ── Todo List ─────────────────────────────────────────────────────────────────


class TodoStatus(str, Enum):
    PENDING = "pending"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class TodoItem:
    description: str
    status: TodoStatus = TodoStatus.PENDING
    result: str = ""

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
            i.status in (TodoStatus.DONE, TodoStatus.SKIPPED) for i in self.items
        )

    def pending_count(self) -> int:
        return sum(1 for i in self.items if i.status == TodoStatus.PENDING)

    def as_text(self) -> str:
        if not self.items:
            return ""
        icons = {
            TodoStatus.PENDING: "[ ]",
            TodoStatus.DONE: "[x]",
            TodoStatus.SKIPPED: "[-]",
            TodoStatus.FAILED: "[!]",
        }
        lines = ["Your todo list:"]
        for item in self.items:
            lines.append(f"  {icons[item.status]} {item.description}")
        return "\n".join(lines)


# ── Agent State ───────────────────────────────────────────────────────────────


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


# ── Base Agent ────────────────────────────────────────────────────────────────


class BaseAgent(ABC):
    def __init__(self, llm: Any, agent_name: AgentName) -> None:
        self.llm = llm
        self.name = agent_name
        self._graph = self._build_graph()
        logger.info(f"BaseAgent [{self.name.value}] initialised")

    # ── Abstract ──────────────────────────────────────────────────────────────

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
        if is_interrupted():
            raise InterruptError("Interrupted before agent run")

        todos = self.build_todos(task)
        full_system = self._build_system_with_todos(todos)

        messages: List[BaseMessage] = [SystemMessage(content=full_system)]

        if task.get("context"):
            messages.append(HumanMessage(content=f"Context:\n{task['context']}"))

        messages.append(HumanMessage(content=task["instruction"]))

        output = ""

        for chunk in self._graph.stream({"messages": messages}):
            if is_interrupted():
                raise InterruptError("Interrupted during agent execution")
            node_name = list(chunk.keys())[0]
            state = chunk[node_name]

            if node_name == "llm" and state.get("messages"):
                last_msg = state["messages"][-1]
                logger.info(f"{self.name.value}: llm step completed")
                if hasattr(last_msg, "content") and last_msg.content:
                    if not getattr(last_msg, "tool_calls", None):
                        output = last_msg.content.strip()
                        print(f"  💬 Agent answered")

            if node_name == "tools" and state.get("messages"):
                last_msg = state["messages"][-1]
                if hasattr(last_msg, "name"):
                    print(f"  🔧 Tool ran: {last_msg.name}")

        duration_ms = int((time.time() - start_time) * 1000)
        logger.info(f"BaseAgent [{self.name.value}] done in {duration_ms}ms")
        return make_task_result(task=task, output=output, success=bool(output))

    # ── LangGraph nodes ───────────────────────────────────────────────────────

    def _llm_node(self, state: AgentState) -> dict:
        if is_interrupted():
            raise InterruptError("Interrupted before LLM call")
        msgs = self._compact_messages(state["messages"])
        print(f"\n  🧠 Thinking... ({len(msgs)} messages in context)")

        bound = self.llm.bind_tools(self.tools) if self.tools else self.llm
        response = bound.invoke(msgs)
        record_usage(f"{self.name.value}.llm", response)

        if getattr(response, "tool_calls", None):
            for tc in response.tool_calls:
                print(f"  📌 Will call: {tc['name']}")

        return {"messages": [response]}

    def _tool_node(self, state: AgentState) -> dict:
        if is_interrupted():
            raise InterruptError("Interrupted before tool execution")
        last = state["messages"][-1]
        tool_map = {t.name: t for t in self.tools}
        results = []

        for tc in last.tool_calls:
            if is_interrupted():
                raise InterruptError("Interrupted during tool execution")
            tool_fn = tool_map.get(tc["name"])
            print(f"\n  ⚙️  Running: {tc['name']}({list(tc.get('args', {}).keys())})")

            if tool_fn is None:
                output = f"ERROR: unknown tool '{tc['name']}'"
                success = False
            else:
                try:
                    output = tool_fn.invoke(tc.get("args", {}))
                    success = True
                except Exception as e:
                    output = f"ERROR: {e}"
                    success = False

            icon = "✅" if success else "❌"
            print(f"  {icon} Done: {tc['name']}")

            results.append(
                ToolMessage(
                    content=str(output),
                    tool_call_id=tc["id"],
                    name=tc["name"],
                )
            )

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
        g.add_node("llm", self._llm_node)
        g.add_node("tools", self._tool_node)

        g.add_edge(START, "llm")
        g.add_conditional_edges(
            "llm",
            self._should_continue,
            {
                "tools": "tools",
                END: END,
            },
        )
        g.add_edge("tools", "llm")

        return g.compile()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_system_with_todos(self, todos: TodoList) -> str:
        base = self.system_prompt.strip()
        todo_text = todos.as_text()
        if todo_text:
            return f"{base}\n\n{todo_text}"
        return base

    def _compact_messages(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """
        Keep critical messages and trim older low-value chatter by token budget.
        """
        print("\n" + "-" * 80)
        print(
            f"[AGENT DEBUG] ══ _compact_messages() START (Agent: {self.name.value}) ══"
        )
        print(f"  Budget: {AGENT_MESSAGE_BUDGET_TOKENS} tokens")

        if not messages:
            print("[AGENT DEBUG] No messages, returning empty")
            return messages

        # Calculate current tokens for each message
        msg_stats = []
        for i, m in enumerate(messages):
            content = getattr(m, "content", "") or ""
            tokens = estimate_tokens(content) + 16
            msg_type = type(m).__name__
            preview = content[:50] + "..." if len(content) > 50 else content
            msg_stats.append((i, msg_type, len(content), tokens, preview))

        total_current = sum(s[3] for s in msg_stats)
        print(f"  Total messages: {len(messages)}")
        print(f"  Current total tokens: {total_current}")
        print(f"  Budget: {AGENT_MESSAGE_BUDGET_TOKENS} tokens")

        print("\n  [Message breakdown:]")
        for i, msg_type, chars, tokens, preview in msg_stats:
            marker = "→" if tokens > 100 else " "
            print(
                f"    [{i:2}] {marker} {msg_type:20} | {chars:5} chars | ~{tokens:4} tokens | {preview}"
            )

        if total_current <= AGENT_MESSAGE_BUDGET_TOKENS:
            print(f"\n[AGENT DEBUG] Within budget, no compaction needed")
            print(f"-" * 80 + "\n")
            return messages

        budget_tokens = AGENT_MESSAGE_BUDGET_TOKENS
        current_tokens = total_current
        print(f"\n[AGENT DEBUG] OVER BUDGET - Starting compaction!")

        system_idx = next(
            (i for i, msg in enumerate(messages) if isinstance(msg, SystemMessage)),
            None,
        )
        last_user_idx = next(
            (
                i
                for i in range(len(messages) - 1, -1, -1)
                if isinstance(messages[i], HumanMessage)
            ),
            None,
        )
        last_tool_idx = next(
            (
                i
                for i in range(len(messages) - 1, -1, -1)
                if isinstance(messages[i], ToolMessage)
            ),
            None,
        )

        protected = {
            idx for idx in (system_idx, last_user_idx, last_tool_idx) if idx is not None
        }
        print(f"\n  [Protected indices:]")
        for idx in protected:
            m = messages[idx]
            content = getattr(m, "content", "") or ""
            tokens = estimate_tokens(content) + 16
            print(f"    [{idx}] {type(m).__name__} ({tokens} tokens) - PROTECTED")

        kept_idx = set(protected)
        total = sum(
            estimate_tokens(getattr(messages[i], "content", "") or "") + 16
            for i in kept_idx
        )

        print(f"\n  [Compaction iteration (newest to oldest):]")
        added_count = 0
        for idx in range(len(messages) - 1, -1, -1):
            if idx in kept_idx:
                continue
            candidate = messages[idx]
            candidate_content = getattr(candidate, "content", "") or ""
            candidate_tokens = estimate_tokens(candidate_content) + 16
            msg_type = type(candidate).__name__
            preview = (
                candidate_content[:40] + "..."
                if len(candidate_content) > 40
                else candidate_content
            )

            if total + candidate_tokens > budget_tokens:
                print(
                    f"    [{idx}] {msg_type} - SKIPPED (budget full: {total} + {candidate_tokens} > {budget_tokens})"
                )
                continue
            kept_idx.add(idx)
            total += candidate_tokens
            added_count += 1
            print(f"    [{idx}] {msg_type} - ADDED ({total} tokens) | {preview}")

        compacted = [msg for i, msg in enumerate(messages) if i in kept_idx]
        compacted_tokens = sum(
            estimate_tokens(getattr(m, "content", "") or "") + 16 for m in compacted
        )

        print(f"\n[AGENT DEBUG] ══ Compaction Complete ══")
        print(f"  Messages: {len(messages)} -> {len(compacted)}")
        print(f"  Tokens: {current_tokens} -> {compacted_tokens}")
        print(f"  Messages added: {added_count}")
        print(
            f"  Budget usage: {compacted_tokens}/{budget_tokens} ({compacted_tokens / budget_tokens * 100:.1f}%)"
        )
        print(f"-" * 80 + "\n")

        return compacted

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(agent={self.name.value!r})"
