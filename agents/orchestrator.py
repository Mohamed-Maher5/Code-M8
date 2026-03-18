"""
orchestrator.py
===============
Orchestrator agent — the only agent that plans, routes, and decides.

Model  : Hunter Alpha via OpenRouter
Tools  : list_files, read_file + subagent tools (explorer, coder)
Role   : Receives user request → builds Plan → delegates → synthesises answer

Rules:
    - Explorer ALWAYS runs before Coder
    - Orchestrator digests Explorer output before passing to Coder
    - Never forwards Explorer output raw to Coder
    - Only agent that speaks to the user
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool

from agents.base_agent import BaseAgent, TodoList
from core import config
from core.types import (
    AgentName,
    Plan,
    Task,
    TaskResult,
    make_task,
    make_task_result,
)


# ══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATOR DIRECT TOOLS  (lightweight — for quick lookups only)
# ══════════════════════════════════════════════════════════════════════════════

@tool
def list_workspace(directory: str = ".") -> str:
    """List files in the workspace. Used for quick overview before planning."""
    workspace = Path(config.WORKSPACE_PATH).resolve()
    target    = (workspace / directory).resolve()

    if not str(target).startswith(str(workspace)):
        return f"ERROR: path outside workspace."
    if not target.exists():
        return f"ERROR: directory not found: {directory}"

    lines: List[str] = []
    for item in sorted(target.rglob("*")):
        parts = item.relative_to(workspace).parts
        if any(p in config.IGNORED_DIRS for p in parts):
            continue
        if item.suffix in config.IGNORED_EXTENSIONS:
            continue
        depth  = len(item.relative_to(workspace).parts) - 1
        indent = "  " * depth
        icon   = "📁" if item.is_dir() else "📄"
        lines.append(f"{indent}{icon} {item.name}")

    return "\n".join(lines) if lines else "(workspace is empty)"


# ══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATOR AGENT
# ══════════════════════════════════════════════════════════════════════════════

class Orchestrator(BaseAgent):
    """
    Orchestrator agent powered by Hunter Alpha via OpenRouter.

    This agent is the entry point for every user request.
    It does NOT execute tasks itself — it plans and delegates.

    Extra methods beyond BaseAgent.run():
        plan()     → builds an ordered Plan from user request
        digest()   → rewrites Explorer output into a clean Coder instruction
        replan()   → rebuilds Plan after a test failure
        summarize()→ writes the final user-facing answer
    """

    def __init__(
        self,
        llm:              Any,
        explorer_fn:      Optional[Callable] = None,
        coder_fn:         Optional[Callable] = None,
        test_runner_fn:   Optional[Callable] = None,
    ) -> None:
        """
        llm           — Hunter Alpha LangChain client
        explorer_fn   — callable: (Task) → TaskResult  (injected by dispatcher)
        coder_fn      — callable: (Task) → TaskResult
        test_runner_fn— callable: (Task) → TaskResult
        """
        super().__init__(llm=llm, agent_name=AgentName.ORCHESTRATOR)
        self._explorer_fn    = explorer_fn
        self._coder_fn       = coder_fn
        self._test_runner_fn = test_runner_fn

    # ── system_prompt ─────────────────────────────────────────────────────────

    @property
    def system_prompt(self) -> str:
                return (
            "You are the Orchestrator of an AI coding assistant.\n"
            "\n"
            "YOUR JOB:\n"
            "  Analyse the user request, pick ONLY the agents needed, and return a JSON plan.\n"
            "\n"
            "YOUR SPECIALISTS:\n"
            "  explorer  — reads files, searches code, explains structure. No side effects.\n"
            "  coder     — writes new files or edits existing ones. Needs explorer context first.\n"
            "  runner    — runs tests on code the coder just wrote. Only after coder.\n"
            "\n"
            "DECIDING WHICH AGENTS TO USE:\n"
            "\n"
            "  READ / SEARCH / EXPLAIN tasks  (explorer only)\n"
            "    Signals: 'explain', 'what does', 'how does', 'find', 'search',\n"
            "             'show me', 'list', 'where is', 'read', 'understand'\n"
            "    Use: explorer only. No coder. No runner.\n"
            "    Example: 'explain how authentication works'\n"
            "             → explorer reads the auth files and explains.\n"
            "\n"
            "  WRITE / IMPLEMENT / FIX tasks  (explorer + coder + runner)\n"
            "    Signals: 'add', 'create', 'implement', 'write', 'build',\n"
            "             'fix', 'refactor', 'edit', 'update', 'change'\n"
            "    Use: explorer first, then coder, then runner.\n"
            "    Example: 'add a /health endpoint'\n"
            "             → explorer reads app, coder writes code, runner tests it.\n"
            "\n"
            "  MIXED tasks  (explorer + coder + runner)\n"
            "    When in doubt, include all three.\n"
            "\n"
            "RULES (always apply):\n"
            "  - explorer ALWAYS runs before coder.\n"
            "  - runner ALWAYS runs after coder, never before.\n"
            "  - Never include runner without coder.\n"
            "  - Never include coder without explorer before it.\n"
            "  - Digest explorer output yourself — never forward it raw to coder.\n"
            "\n"
            "OUTPUT FORMAT:\n"
            "  Return a single JSON object. No markdown. No extra text.\n"
            "  {\n"
            '    "task_type": "read" or "write",\n'
            '    "reasoning": "one sentence explaining your plan",\n'
            '    "steps": [\n'
            '      {"agent": "explorer", "instruction": "specific instruction"},\n'
            '      {"agent": "coder",    "instruction": "specific instruction"},\n'
            '      {"agent": "runner",   "instruction": "run tests on changed files"}\n'
            "    ]\n"
            "  }\n"
            "\n"
            "  For read-only tasks, steps contains only explorer:\n"
            '  {"task_type": "read", "reasoning": "...", "steps": [\n'
            '    {"agent": "explorer", "instruction": "..."}\n'
            "  ]}\n"
            "\n"
            "  Instructions must be specific — mention actual file names if you know them."
        )
    @property
    def tools(self) -> List[Any]:
        return [list_workspace]

    def build_todos(self, task: Task) -> TodoList:
        todos = TodoList()
        todos.add("understand the user request")
        todos.add("build an execution plan")
        todos.add("delegate to Explorer")
        todos.add("digest findings and instruct Coder")
        todos.add("delegate to Coder")
        todos.add("run tests via TestRunner")
        todos.add("write final answer for user")
        return todos

    # ══════════════════════════════════════════════════════════════════════════
    # EXTRA METHODS — beyond what BaseAgent provides
    # ══════════════════════════════════════════════════════════════════════════

    def plan(self, user_request: str, session_history: List[str] = []) -> Plan:
        """
        Calls Hunter Alpha to build an ordered Plan from the user request.
        Returns a Plan (list of Tasks in correct order).

        Called by loop.py at the start of every user turn.
        """
        history_text = "\n".join(session_history[-10:]) if session_history else ""

        prompt = (
            f"User request: {user_request}\n\n"
            + (f"Recent history:\n{history_text}\n\n" if history_text else "")
            + "Build a plan. Return JSON only — no other text."
        )

        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt),
        ]

        response = self.llm.invoke(messages)
        content  = response.content if isinstance(response, AIMessage) else str(response)

        return self._parse_plan(content, user_request)

    def digest(self, explorer_result: TaskResult, original_request: str) -> str:
        """
        Receives Explorer's raw findings and rewrites them as a clean,
        precise instruction for the Coder.

        This is the critical step that separates Explorer from Coder.
        Coder never sees raw Explorer output — only Orchestrator's digest.

        Called by loop.py after Explorer finishes.
        """
        prompt = (
            f"Original user request:\n{original_request}\n\n"
            f"Explorer findings:\n{explorer_result['output']}\n\n"
            "Based on the findings above, write a precise instruction for the Coder.\n"
            "The instruction must say exactly:\n"
            "  - Which files to create\n"
            "  - Which files to edit and what changes to make\n"
            "  - What the code must do\n"
            "  - Any patterns or conventions to follow from the existing code\n"
            "Write the Coder instruction only. No other text."
        )

        messages = [
            SystemMessage(content="You are the Orchestrator. Write a precise Coder instruction."),
            HumanMessage(content=prompt),
        ]

        response = self.llm.invoke(messages)
        return response.content.strip() if isinstance(response, AIMessage) else str(response)

    def replan(
        self,
        original_request:  str,
        failed_output:     str,
        test_errors:       str,
        attempt_number:    int,
    ) -> Plan:
        """
        Called by retry_controller when tests fail.
        Decides whether to re-run Explorer (for more context)
        or go straight to Coder (just fix the error).

        attempt 1 → explore again first
        attempt 2+ → skip Explorer, fix Coder directly
        """
        prompt = (
            f"User request: {original_request}\n\n"
            f"Coder produced this code:\n{failed_output}\n\n"
            f"Tests failed with:\n{test_errors}\n\n"
            f"This is attempt {attempt_number}.\n"
            + (
                "Decide: do you need more context (run Explorer again) "
                "or just fix the code directly?\n"
                if attempt_number == 1
                else "Fix the code directly — no need to explore again.\n"
            )
            + "Return a JSON plan. explorer steps before coder steps. runner last."
        )

        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt),
        ]

        response = self.llm.invoke(messages)
        content  = response.content if isinstance(response, AIMessage) else str(response)

        return self._parse_plan(content, original_request)

    def summarize(
        self,
        user_request:  str,
        all_results:   List[TaskResult],
        tests_passed:  bool,
    ) -> str:
        """
        Called by synthesizer.py after all tasks complete.
        Writes the final human-readable answer shown to the user.
        """
        results_text = "\n\n".join(
            f"[{r['task']['agent'].upper()}]:\n{r['output']}"
            for r in all_results
        )

        prompt = (
            f"User request: {user_request}\n\n"
            f"Results from all agents:\n{results_text}\n\n"
            f"Tests {'passed ✅' if tests_passed else 'failed ❌'}.\n\n"
            "Write a clear, concise summary for the user:\n"
            "  - What was done\n"
            "  - Which files were created or changed\n"
            "  - Test result\n"
            "  - What to do next (if anything)\n"
            "Speak directly to the user. Be concise."
        )

        messages = [
            SystemMessage(content="You are the Orchestrator. Write the final answer for the user."),
            HumanMessage(content=prompt),
        ]

        response = self.llm.invoke(messages)
        return response.content.strip() if isinstance(response, AIMessage) else str(response)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _parse_plan(self, llm_output: str, original_request: str) -> Plan:
        """
        Parses the LLM's JSON plan output into a Plan TypedDict.
        Falls back to a safe default plan if parsing fails.
        """
        # Strip markdown code fences if present
        text = llm_output.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text  = "\n".join(lines[1:-1]) if len(lines) > 2 else text

        try:
            data  = json.loads(text)
            steps = data.get("steps", [])
            tasks = [
                make_task(
                    agent       = step["agent"],
                    instruction = step["instruction"],
                    context     = "",
                )
                for step in steps
                if step.get("agent") in ("explorer", "coder", "runner")
            ]

            # Enforce ordering: explorer before coder, runner last
            tasks = self._enforce_order(tasks)

            return Plan(steps=tasks)

        except (json.JSONDecodeError, KeyError, TypeError):
            # Fallback plan — explore then code then test
            return Plan(steps=[
                make_task("explorer", f"Explore the codebase for: {original_request}"),
                make_task("coder",    f"Implement: {original_request}"),
                make_task("runner",   "Run tests on the changes"),
            ])

    def _enforce_order(self, tasks: List[Task]) -> List[Task]:
        """
        Reorders tasks so explorer steps come before coder steps,
        and runner step is always last.
        Raises PlanViolation is there are no tasks.
        """
        explorers = [t for t in tasks if t["agent"] == "explorer"]
        coders    = [t for t in tasks if t["agent"] == "coder"]
        runners   = [t for t in tasks if t["agent"] == "runner"]
        others    = [t for t in tasks if t["agent"] not in ("explorer", "coder", "runner")]

        return explorers + coders + runners + others