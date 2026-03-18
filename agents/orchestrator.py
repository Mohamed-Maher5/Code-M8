# agents/orchestrator.py
# Orchestrator agent — plans, routes, and decides
# Model  : Hunter Alpha via OpenRouter
# Role   : Receives user request → builds Plan → delegates → synthesises answer
# Rules  :
#     - Explorer ALWAYS runs before Coder
#     - Orchestrator digests Explorer output before passing to Coder
#     - Never forwards Explorer output raw to Coder
#     - Only agent that speaks to the user

from __future__ import annotations

import json
from typing import Any, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.base_agent import BaseAgent, TodoList
from core.types import (
    AgentName,
    Plan,
    Task,
    TaskResult,
    make_task,
)
from utils.logger import logger


# ── Orchestrator Agent ────────────────────────────────────────────────────────

class Orchestrator(BaseAgent):

    def __init__(self, llm: Any) -> None:
        super().__init__(llm=llm, agent_name=AgentName.ORCHESTRATOR)

        # injected by dispatcher when tools are ready
        # self._explorer_fn    = None
        # self._coder_fn       = None
        # self._test_runner_fn = None

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
        # no tools yet — list_workspace will be added in the next task
        return []

    def build_todos(self, task: Task) -> TodoList:
        todos = TodoList()
        todos.add("understand the user request")
        todos.add("build an execution plan")
        todos.add("delegate to Explorer")
        todos.add("digest findings and instruct Coder")
        todos.add("delegate to Coder")
        todos.add("write final answer for user")
        return todos

    # ── plan() ────────────────────────────────────────────────────────────────

    def plan(self, user_request: str, session_history: List[str] = []) -> Plan:
        # asks Hunter to build an ordered Plan from the user request
        # called by loop.py at the start of every user turn
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

        logger.info("Orchestrator: plan built")
        return self._parse_plan(content, user_request)

    # ── digest() ──────────────────────────────────────────────────────────────

    def digest(self, explorer_result: TaskResult, original_request: str) -> str:
        # rewrites Explorer's raw findings into a clean Coder instruction
        # coder never sees raw Explorer output — only Orchestrator's digest
        # called by loop.py after Explorer finishes
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
        logger.info("Orchestrator: digest done")
        return response.content.strip() if isinstance(response, AIMessage) else str(response)

    # ── summarize() ───────────────────────────────────────────────────────────

    def summarize(
        self,
        user_request: str,
        all_results  : List[TaskResult],
        tests_passed : bool,
    ) -> str:
        # writes the final human-readable answer shown to the user
        # called by synthesizer.py after all tasks complete
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
        logger.info("Orchestrator: summarize done")
        return response.content.strip() if isinstance(response, AIMessage) else str(response)

    # ── replan() — uncomment in Task 3 when retry controller is ready ─────────

    # def replan(
    #     self,
    #     original_request: str,
    #     failed_output    : str,
    #     test_errors      : str,
    #     attempt_number   : int,
    # ) -> Plan:
    #     prompt = (
    #         f"User request: {original_request}\n\n"
    #         f"Coder produced this code:\n{failed_output}\n\n"
    #         f"Tests failed with:\n{test_errors}\n\n"
    #         f"This is attempt {attempt_number}.\n"
    #         + (
    #             "Decide: do you need more context (run Explorer again) "
    #             "or just fix the code directly?\n"
    #             if attempt_number == 1
    #             else "Fix the code directly — no need to explore again.\n"
    #         )
    #         + "Return a JSON plan. explorer steps before coder steps. runner last."
    #     )
    #     messages = [
    #         SystemMessage(content=self.system_prompt),
    #         HumanMessage(content=prompt),
    #     ]
    #     response = self.llm.invoke(messages)
    #     content  = response.content if isinstance(response, AIMessage) else str(response)
    #     return self._parse_plan(content, original_request)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _parse_plan(self, llm_output: str, original_request: str) -> Plan:
        # parses the LLM's JSON plan output into a Plan TypedDict
        # falls back to a safe default plan if parsing fails
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
            tasks = self._enforce_order(tasks)
            return Plan(steps=tasks)

        except (json.JSONDecodeError, KeyError, TypeError):
            logger.warning("Orchestrator: plan parsing failed — using fallback")
            return Plan(steps=[
                make_task("explorer", f"Explore the codebase for: {original_request}"),
                make_task("coder",    f"Implement: {original_request}"),
            ])

    def _enforce_order(self, tasks: List[Task]) -> List[Task]:
        # guarantees explorer → coder → runner order
        explorers = [t for t in tasks if t["agent"] == "explorer"]
        coders    = [t for t in tasks if t["agent"] == "coder"]
        runners   = [t for t in tasks if t["agent"] == "runner"]
        others    = [t for t in tasks if t["agent"] not in ("explorer", "coder", "runner")]
        return explorers + coders + runners + others