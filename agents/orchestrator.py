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
from core.token_usage import record_usage
from core.types import (
    AgentName,
    Plan,
    Task,
    TaskResult,
    make_task,
)
from context.token_budget import estimate_tokens
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
            "  Classify the request into ONE of these categories:\n"
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
            "     → NO:  Use explorer to explore, then decide\n"
            "\n"
            "RULES (always apply):\n"
            "  1. explorer ALWAYS runs before coder for any write operation\n"
            "  2. Never forward raw explorer output to coder - digest it first\n"
            "  3. For SEARCH requests → search WIDELY, don't narrow to history files\n"
            "  4. Be specific in instructions - mention file patterns or locations\n"
            "\n"
            "OUTPUT FORMAT:\n"
            "  Return a single JSON object. No markdown. No extra text.\n"
            "  {\n"
            '    "task_type": "read" | "write",\n'
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
            "  Key: Be explicit about SEARCH SCOPE in explorer instructions.\n"
            "       Say 'search ENTIRE workspace' when appropriate.\n"
        )

    @property
    def tools(self) -> List[Any]:
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
        record_usage("orchestrator.plan", response)
        content = response.content if isinstance(response, AIMessage) else str(response)
        logger.info("Orchestrator: plan built")
        return self._parse_plan(content, user_request)

    # ── digest() ──────────────────────────────────────────────────────────────

    def digest(self, explorer_result: TaskResult, original_request: str) -> str:
        prompt = (
            f"Original user request:\n{original_request}\n\n"
            f"Explorer findings:\n{explorer_result['output']}\n\n"
            "Based on the findings above, write a precise instruction for the Coder.\n"
            "The instruction must say exactly:\n"
            "  - Which files to create, including the exact filename and extension\n"
            "  - Which files to edit and what changes to make\n"
            "  - What the code must do\n"
            "  - Any patterns or conventions to follow from the existing code\n"
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

    # ── summarize() ───────────────────────────────────────────────────────────

    def summarize(
        self,
        user_request: str,
        all_results: List[TaskResult],
        tests_passed: bool,
    ) -> str:
        print("\n" + "=" * 80)
        print("[SUMMARIZE DEBUG] ══ orchestrator.summarize() START ══")
        print(
            f"  User request: {user_request[:100]}{'...' if len(user_request) > 100 else ''}"
        )
        print(f"  Tests passed: {tests_passed}")
        print(f"  Results count: {len(all_results)}")

        for i, r in enumerate(all_results):
            agent = r["task"]["agent"]
            output_len = len(r["output"])
            print(f"    Result {i + 1}: [{agent.upper()}] - {output_len} chars")

        results_text = "\n\n".join(
            f"[{r['task']['agent'].upper()}]:\n{r['output']}" for r in all_results
        )
        results_text_len = len(results_text)
        print(
            f"\n  Combined results text: {results_text_len} chars, ~{estimate_tokens(results_text)} tokens"
        )

        prompt = (
            f"User request: {user_request}\n\n"
            f"Results from all agents:\n{results_text}\n\n"
            "Write a clear answer for the user:\n"
            "  - What was done\n"
            "  - Which files were involved\n"
            "  - If code snippets appear in results, preserve them VERBATIM in your answer\n"
            "  - Only suggest next steps if they are explicitly mentioned in the results above (do not invent new suggestions)\n"
            "Speak directly to the user. Preserve all code blocks exactly as shown."
        )
        prompt_len = len(prompt)
        prompt_tokens = estimate_tokens(prompt)
        print(f"  Prompt to LLM: {prompt_len} chars, ~{prompt_tokens} tokens")

        messages = [
            SystemMessage(
                content="You are the Orchestrator. Write the final answer for the user."
            ),
            HumanMessage(content=prompt),
        ]

        system_msg_len = len(
            "You are the Orchestrator. Write the final answer for the user."
        )
        print(
            f"  System message: {system_msg_len} chars, ~{estimate_tokens(messages[0].content)} tokens"
        )
        print(
            f"  Total input to LLM: ~{estimate_tokens(messages[0].content) + prompt_tokens} tokens"
        )

        print("\n[SUMMARIZE DEBUG] Calling LLM...")
        response = self.llm.invoke(messages)
        print("[SUMMARIZE DEBUG] LLM response received")

        record_usage("orchestrator.summarize", response)
        logger.info("Orchestrator: summarize done")

        result = (
            response.content.strip()
            if isinstance(response, AIMessage)
            else str(response)
        )

        result_len = len(result)
        result_tokens = estimate_tokens(result)
        print(f"\n[SUMMARIZE DEBUG] ══ orchestrator.summarize() COMPLETE ══")
        print(f"  Response: {result_len} chars, ~{result_tokens} tokens")
        print(f"  Response preview: {result[:100]}{'...' if result_len > 100 else ''}")
        print("=" * 80 + "\n")

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
