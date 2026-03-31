# agents/orchestrator.py
# Orchestrator agent — plans, routes, and decides.
# Now spec-aware: plan() calls read_spec if user provides a spec source,
# and digest() injects acceptance criteria into every Coder instruction.

from __future__ import annotations

import json
from typing import Any, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.base_agent import BaseAgent, TodoList
from core.token_usage import record_usage
from core.types import (
    AgentName,
    Plan,
    Task,
    TaskResult,
    make_task,
)
from core.token_usage import estimate_tokens
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
            "  Analyse the user request, check the provided context/memory, and return a JSON plan.\n"
            "  Pick ONLY the agents needed for the task.\n"
            "\n"
            "YOUR SPECIALISTS:\n"
            "  explorer  — searches code, reads files, finds patterns, explains structure.\n"
            "             Use this agent to FIND or UNDERSTAND existing code.\n"
            "             This agent has NO side effects - it only reads and reports.\n"
            "  coder     — writes new files or edits existing code.\n"
            "             Use this agent to CREATE or MODIFY code.\n"
            "             Requires explorer context first to understand the codebase.\n"
            "\n"
            "UNDERSTANDING THE USER REQUEST:\n"
            "\n"
            "  1. SEARCH / FIND / UNDERSTAND (READ-ONLY)\n"
            "     User wants to FIND existing code, EXPLAIN how something works,\n"
            "     or UNDERSTAND the codebase.\n"
            "     Signals: where, find, search, show, explain, how does, what is,\n"
            "              list, read, understand, trace, locate, get, retrieve\n"
            "     Action: Use ONLY explorer. No coder needed.\n"
            "     Example: 'where is the pop logic'\n"
            "              → Search ENTIRE workspace for 'pop' logic\n"
            "\n"
            "  2. CREATE / ADD / WRITE (WRITE)\n"
            "     User wants to ADD something new or CREATE a new file.\n"
            "     Signals: create, add, make new, write new, implement new,\n"
            "              build, generate, init\n"
            "     Action: Use explorer first (to avoid conflicts), then coder.\n"
            "     Example: 'create a new helper function'\n"
            "              → explorer finds where helpers go, coder writes it\n"
            "\n"
            "  3. EDIT / FIX / MODIFY / UPDATE (WRITE)\n"
            "     User wants to CHANGE existing code.\n"
            "     Signals: fix, edit, update, change, modify, refactor,\n"
            "              remove, delete, replace, improve, optimize\n"
            "     Action: Use explorer first (to find the code), then coder.\n"
            "     Example: 'fix the bug in auth'\n"
            "              → explorer finds auth code, coder fixes it\n"
            "\n"
            "  4. TEST / VERIFY / RUN (TEST)\n"
            "     User wants to RUN TESTS or VERIFY code works.\n"
            "     Signals: test, verify, run test, check function, check method,\n"
            "              run the code, execute test\n"
            "     Action: Use explorer first (find the code), then coder.\n"
            "     Example: 'test the add function'\n"
            "              → explorer finds the function, coder runs inline test\n"
            "     IMPORTANT: Coder will run inline tests and print results.\n"
            "\n"
            "USING CONTEXT/MEMORY EFFECTIVELY:\n"
            "\n"
            "  The history provides HINTS about the codebase, NOT directives.\n"
            "\n"
            "  RULES FOR USING HISTORY:\n"
            "  - Previous file mentions are SUGGESTIONS, not requirements\n"
            "  - If user asks to FIND something → search ENTIRE workspace\n"
            "  - If user asks to CREATE → check history for file naming patterns\n"
            "  - Ignore irrelevant history when the request is clear\n"
            "  - When in doubt about which files → default to searching more files\n"
            "\n"
            "  GOOD: 'User wants pop logic - history mentions validators.py but\n"
            "         pop could be anywhere - search whole workspace'\n"
            "\n"
            "  BAD:  'History mentions validators.py - only search that file'\n"
            "\n"
            "DECISION TREE:\n"
            "\n"
            "  Q: Does user want to FIND/READ/UNDERSTAND existing code?\n"
            "     → YES: Use explorer. Search ENTIRE workspace (not just history files)\n"
            "     → NO:  Continue\n"
            "\n"
            "  Q: Does user want to CREATE/ADD new code?\n"
            "     → YES: Use explorer (check patterns) → coder (write)\n"
            "     → NO:  Continue\n"
            "\n"
            "  Q: Does user want to EDIT/CHANGE existing code?\n"
            "     → YES: Use explorer (find code) → coder (edit)\n"
            "     → NO:  Continue\n"
            "\n"
            "  Q: Does user want to TEST/VERIFY/RUN code?\n"
            "     → YES: Use explorer (find function) → coder (run inline test)\n"
            "     → NO:  Use explorer to explore, then decide\n"
            "\n"
            "RULES (always apply):\n"
            "  1. explorer ALWAYS runs before coder for any write operation\n"
            "  2. Never forward raw explorer output to coder - digest it first\n"
            "  3. For SEARCH requests → search WIDELY, don't narrow to history files\n"
            "  4. For TEST requests → coder must run inline test and print results\n"
            "  5. Be specific in instructions - mention file patterns or locations\n"
            "\n"
            "OUTPUT FORMAT:\n"
            "  Return a single JSON object. No markdown. No extra text.\n"
            "  {\n"
            '    "task_type": "read" | "write" | "test",\n'
            '    "reasoning": "one sentence explaining your plan and how you used context",\n'
            '    "steps": [\n'
            '      {"agent": "explorer", "instruction": "specific instruction - include search scope"},\n'
            '      {"agent": "coder",    "instruction": "specific instruction - include file path"}\n'
            "    ]\n"
            "  }\n"
            "\n"
            "  For READ-ONLY tasks (search/explore):\n"
            '  {"task_type": "read", "reasoning": "...", "steps": [\n'
            '    {"agent": "explorer", "instruction": "Search ENTIRE workspace for X - check all relevant files"}\n'
            "  ]}\n"
            "\n"
            "  For WRITE tasks:\n"
            '  {"task_type": "write", "reasoning": "...", "steps": [\n'
            '    {"agent": "explorer", "instruction": "Find existing patterns in workspace for X"},\n'
            '    {"agent": "coder",    "instruction": "Create/edit file Y with Z"}\n'
            "  ]}\n"
            "\n"
            "  For TEST tasks (test/verify code):\n"
            '  {"task_type": "test", "reasoning": "...", "steps": [\n'
            '    {"agent": "explorer", "instruction": "Find the function/class to test in workspace"},\n'
            '    {"agent": "coder",    "instruction": "Use run_test to run inline tests - NO files allowed"}\n'
            "  ]}\n"
            "\n"
            "  Key: Be explicit about SEARCH SCOPE in explorer instructions.\n"
            "       Say 'search ENTIRE workspace' when appropriate.\n"
            "  For TEST tasks: coder MUST use run_test tool, NEVER create test files.\n"
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
        record_usage("orchestrator.plan", response)
        content = response.content if isinstance(response, AIMessage) else str(response)
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
            parsed = json.loads(raw_json)

            if isinstance(parsed, dict) and "error" in parsed:
                logger.warning(f"Orchestrator: spec parse error — {parsed['error']}")
                return f"[Spec load failed: {parsed['error']}]"

            if isinstance(parsed, list):
                spec_store.set_criteria(parsed, source=source)
                logger.info(
                    f"Orchestrator: stored {len(parsed)} criteria from '{source}'"
                )
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
            "IMPORTANT: If user wants to TEST/VERIFY code:\n"
            "  - DO NOT create any test files (no test_*.py)\n"
            "  - Use run_test tool with inline Python code\n"
            '  - Example: run_test(code="result = add(1,2); print(f\'1+2={result}\')", imports="from math import add")\n'
            "  - Print test results in terminal with PASS/FAIL indicators\n"
            "\n"
            "╔═══════════════════════════════════════════════════════════════════╗\n"
            "║  CRITICAL: FILE PATH FORMAT                                       ║\n"
            "╚═══════════════════════════════════════════════════════════════════╝\n"
            "When specifying file paths for the Coder:\n"
            "  - Use SIMPLE relative paths: math_utils.py, data_structures.py\n"
            "  - NEVER prefix with: workspace/, M8/, Code-M8/, ./, or full paths\n"
            "  - WRONG:  workspace/new_file.py, M8/workspace/math_utils.py\n"
            "  - RIGHT:  new_file.py, math_utils.py\n"
            "  - The coder tools automatically resolve paths to the workspace directory\n"
            "\n"
            "IMPORTANT RULES FOR CODER INSTRUCTION:\n"
            "  - If the file already exists → tell Coder to use edit_file, never write_file\n"
            "  - If the file does not exist → tell Coder to use write_file\n"
            "  - Always state the file type explicitly (e.g. .py, .js, .html, .json, .yaml)\n"
            "  - If the user did not specify a file type, infer the correct extension from context:\n"
            "      * Python project → .py\n"
            "      * Web frontend → .html / .css / .js\n"
            "      * Config or data → .json or .yaml\n"
            "      * Documentation → .md\n"
            "  - If the file is binary (image, PDF, compiled asset) → tell Coder to use write_file with is_base64=True\n"
            "  - Always preserve existing code — only add or change what is needed\n"
            "  - Include the exact location in the file where the change must be made\n"
            "\n"
            "Write the Coder instruction only. No other text."
        )
        messages = [
            SystemMessage(
                content="You are the Orchestrator. Write a precise Coder instruction."
            ),
            HumanMessage(content=prompt),
        ]
        response = self.llm.invoke(messages)
        record_usage("orchestrator.digest", response)
        logger.info("Orchestrator: digest done")
        return (
            response.content.strip()
            if isinstance(response, AIMessage)
            else str(response)
        )

    # ── summarize() — cross-references criteria ───────────────────────────────

    def summarize(
        self,
        user_request: str,
        all_results: List[TaskResult],
        tests_passed: bool,
    ) -> str:
        """
        Build the final answer. If criteria are loaded, ask the LLM to assess
        each one explicitly (PASS / PARTIAL / FAIL) based on the agent outputs.
        """
        import core.spec_store as spec_store

        results_text = "\n\n".join(
            f"[{r['task']['agent'].upper()}]:\n{r['output']}" for r in all_results
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
            + (
                "  - Include the criteria checklist with PASS/PARTIAL/FAIL status\n"
                if spec_store.has_spec()
                else ""
            )
            + "Speak directly to the user. Be concise."
        )
        prompt_len = len(prompt)
        prompt_tokens = estimate_tokens(prompt)

        messages = [
            SystemMessage(
                content="You are the Orchestrator. Write the final answer for the user."
            ),
            HumanMessage(content=prompt),
        ]

        response = self.llm.invoke(messages)

        record_usage("orchestrator.summarize", response)
        logger.info("Orchestrator: summarize done")

        result = (
            response.content.strip()
            if isinstance(response, AIMessage)
            else str(response)
        )

        return result

    # ── Private helpers ───────────────────────────────────────────────────────

    def _parse_plan(self, llm_output: str, original_request: str) -> Plan:
        text = llm_output.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

        try:
            data = json.loads(text)
            steps = data.get("steps", [])
            tasks = [
                make_task(
                    agent=step["agent"],
                    instruction=step["instruction"],
                    context="",
                )
                for step in steps
                if step.get("agent") in ("explorer", "coder")
            ]
            tasks = self._enforce_order(tasks)
            return Plan(steps=tasks)

        except (json.JSONDecodeError, KeyError, TypeError):
            logger.warning("Orchestrator: plan parsing failed — using fallback")
            return Plan(
                steps=[
                    make_task(
                        "explorer", f"Explore the codebase for: {original_request}"
                    ),
                    make_task("coder", f"Implement: {original_request}"),
                ]
            )

    def _enforce_order(self, tasks: List[Task]) -> List[Task]:
        explorers = [t for t in tasks if t["agent"] == "explorer"]
        coders = [t for t in tasks if t["agent"] == "coder"]
        others = [t for t in tasks if t["agent"] not in ("explorer", "coder")]
        return explorers + coders + others
