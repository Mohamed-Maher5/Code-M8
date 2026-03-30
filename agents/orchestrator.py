# agents/orchestrator.py
# Orchestrator agent — plans, routes, and decides.
# Now spec-aware: plan() calls read_spec if user provides a spec source,
# and digest() injects acceptance criteria into every Coder instruction.

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


class Orchestrator(BaseAgent):

    def __init__(self, llm: Any) -> None:
        super().__init__(llm=llm, agent_name=AgentName.ORCHESTRATOR)

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
            "\n"
            "DECIDING WHICH AGENTS TO USE:\n"
            "\n"
            "  READ / SEARCH / EXPLAIN tasks  (explorer only)\n"
            "    Signals: 'explain', 'what does', 'how does', 'find', 'search',\n"
            "             'show me', 'list', 'where is', 'read', 'understand'\n"
            "    Use: explorer only. No coder.\n"
            "\n"
            "  WRITE / IMPLEMENT / FIX tasks  (explorer + coder)\n"
            "    Signals: 'add', 'create', 'implement', 'write', 'build',\n"
            "             'fix', 'refactor', 'edit', 'update', 'change'\n"
            "    Use: explorer first, then coder.\n"
            "\n"
            "  MIXED tasks  (explorer + coder)\n"
            "    When in doubt, include both.\n"
            "\n"
            "RULES (always apply):\n"
            "  - explorer ALWAYS runs before coder.\n"
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
            '      {"agent": "coder",    "instruction": "specific instruction"}\n'
            "    ]\n"
            "  }\n"
            "\n"
            "  Instructions must be specific — mention actual file names if you know them."
        )

    @property
    def tools(self) -> List[Any]:
        # read_spec is called directly in plan(), not via the LangGraph tool loop.
        # Returning empty here keeps the orchestrator's own agent loop tool-free,
        # which is correct — the orchestrator reasons and delegates, never reads files.
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

    # ── plan() — now spec-aware ───────────────────────────────────────────────

    def plan(self, user_request: str, session_history: List[str] = []) -> Plan:
        """Build execution plan. If user mentions a spec, parse and store it first."""

        # Step 1 — detect and load spec if referenced in the request
        spec_context = self._maybe_load_spec(user_request)

        history_text = "\n".join(session_history[-10:]) if session_history else ""
        prompt = (
            f"User request: {user_request}\n\n"
            + (f"Recent history:\n{history_text}\n\n" if history_text else "")
            + (f"Loaded spec:\n{spec_context}\n\n" if spec_context else "")
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

    def _maybe_load_spec(self, user_request: str) -> str:
        """
        If the user request references a spec file or provides inline spec text,
        parse it with read_spec, store in SpecStore, and return a summary string
        to inject into the plan prompt.

        Trigger phrases:
          - "using spec <path>"
          - "spec: <path>"
          - "from spec <path>"
          - "requirements: <path>"
          - "prd: <path>"
          - "load spec <path>"
          - "spec file <path>"
        """
        import re
        from tools.read_spec import read_spec as _read_spec_tool
        import core.spec_store as spec_store

        # Pattern: keyword followed by a file path or quoted text
        pattern = re.compile(
            r"(?:using spec|from spec|spec:|spec file|load spec|requirements:|prd:)\s+"
            r"([^\s,;]+)",
            re.IGNORECASE,
        )
        match = pattern.search(user_request)

        if not match:
            # No spec reference — return existing spec summary if one is already loaded
            if spec_store.has_spec():
                return spec_store.as_injection_text()
            return ""

        source = match.group(1).strip().strip('"').strip("'")
        logger.info(f"Orchestrator: detected spec source '{source}'")

        try:
            raw_json = _read_spec_tool.invoke({"source": source})
            parsed   = json.loads(raw_json)

            if isinstance(parsed, dict) and "error" in parsed:
                logger.warning(f"Orchestrator: spec parse error — {parsed['error']}")
                return f"[Spec load failed: {parsed['error']}]"

            if isinstance(parsed, list):
                spec_store.set_criteria(parsed, source=source)
                logger.info(f"Orchestrator: stored {len(parsed)} criteria from '{source}'")
                return spec_store.as_injection_text()

        except Exception as e:
            logger.error(f"Orchestrator: _maybe_load_spec failed — {e}")

        return ""

    # ── digest() — injects criteria into Coder instruction ────────────────────

    def digest(self, explorer_result: TaskResult, original_request: str) -> str:
        """
        Translate Explorer findings into a precise Coder instruction.
        If acceptance criteria are loaded, inject them so the Coder
        writes code that satisfies each criterion explicitly.
        """
        import core.spec_store as spec_store

        criteria_block = spec_store.as_injection_text()

        criteria_instruction = ""
        if criteria_block:
            criteria_instruction = (
                "\n\nIMPORTANT — this task is spec-driven. You MUST satisfy every criterion below.\n"
                "For each [AC-XXX] item marked 'testable', write the implementation such that\n"
                "a pytest test for that criterion would pass.\n\n"
                f"{criteria_block}\n"
                "\nAfter writing the code, add a comment block at the top of each file:\n"
                "  # Implements: AC-001, AC-002, ...\n"
                "listing which criteria that file addresses."
            )

        prompt = (
            f"Original user request:\n{original_request}\n\n"
            f"Explorer findings:\n{explorer_result['output']}\n\n"
            f"{criteria_instruction}\n"
            "Based on the findings above, write a precise instruction for the Coder.\n"
            "The instruction must say exactly:\n"
            "  - Which files to create, including the exact filename and extension\n"
            "  - Which files to edit and what changes to make\n"
            "  - What the code must do\n"
            "  - Any patterns or conventions to follow from the existing code\n"
            "\n"
            "IMPORTANT RULES FOR CODER INSTRUCTION:\n"
            "  - If the file already exists → tell Coder to use edit_file, never write_file\n"
            "  - If the file does not exist → tell Coder to use write_file\n"
            "  - Always state the file type explicitly (e.g. .py, .js, .html, .json, .yaml)\n"
            "  - If the user did not specify a file type, infer the correct extension from context\n"
            "  - Always preserve existing code — only add or change what is needed\n"
            "  - Include the exact location in the file where the change must be made\n"
            "\n"
            "Write the Coder instruction only. No other text."
        )
        messages = [
            SystemMessage(content="You are the Orchestrator. Write a precise Coder instruction."),
            HumanMessage(content=prompt),
        ]
        response = self.llm.invoke(messages)
        logger.info("Orchestrator: digest done")
        return response.content.strip() if isinstance(response, AIMessage) else str(response)

    # ── summarize() — cross-references criteria ───────────────────────────────

    def summarize(
        self,
        user_request : str,
        all_results  : List[TaskResult],
        tests_passed : bool,
    ) -> str:
        """
        Build the final answer. If criteria are loaded, ask the LLM to assess
        each one explicitly (PASS / PARTIAL / FAIL) based on the agent outputs.
        """
        import core.spec_store as spec_store

        results_text = "\n\n".join(
            f"[{r['task']['agent'].upper()}]:\n{r['output']}"
            for r in all_results
        )

        checklist_block = ""
        if spec_store.has_spec():
            checklist_block = (
                "\n\nCRITERIA VERIFICATION — for each criterion below, determine based on the\n"
                "agent outputs whether it was met. Replace ??? with one of:\n"
                "  PASS    — the code clearly satisfies this criterion\n"
                "  PARTIAL — partially addressed but not fully\n"
                "  FAIL    — not addressed at all\n\n"
                f"{spec_store.as_checklist_text()}\n\n"
                "Include the completed checklist in your answer under a '## Criteria status' heading."
            )

        prompt = (
            f"User request: {user_request}\n\n"
            f"Results from all agents:\n{results_text}\n"
            f"{checklist_block}\n\n"
            "Write a clear, concise summary for the user:\n"
            "  - What was done\n"
            "  - Which files were created or changed\n"
            "  - What to do next (if anything)\n"
            + ("  - Include the criteria checklist with PASS/PARTIAL/FAIL status\n"
               if spec_store.has_spec() else "")
            + "Speak directly to the user. Be concise."
        )
        messages = [
            SystemMessage(content="You are the Orchestrator. Write the final answer for the user."),
            HumanMessage(content=prompt),
        ]
        response = self.llm.invoke(messages)
        logger.info("Orchestrator: summarize done")
        return response.content.strip() if isinstance(response, AIMessage) else str(response)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _parse_plan(self, llm_output: str, original_request: str) -> Plan:
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
                if step.get("agent") in ("explorer", "coder")
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
        explorers = [t for t in tasks if t["agent"] == "explorer"]
        coders    = [t for t in tasks if t["agent"] == "coder"]
        others    = [t for t in tasks if t["agent"] not in ("explorer", "coder")]
        return explorers + coders + others