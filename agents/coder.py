# agents/coder.py
# Coder agent — writes and edits files based on Orchestrator instructions
# Model  : MiniMax M2.5 via OpenRouter
# Tools  : write_file, edit_file — imported from tools/

from __future__ import annotations

import re
from typing import Any, List

from agents.base_agent import BaseAgent, TodoList
from core.config import WORKSPACE_PATH
from core.types import AgentName, Task, TaskResult
from tools.tool_registry import CODER_TOOLS


class Coder(BaseAgent):
    def __init__(self, llm: Any) -> None:
        super().__init__(llm=llm, agent_name=AgentName.CODER)
        self._indexed_files: set[str] = set()

    def _ensure_indexed(self, file_path: str) -> None:
        """Auto-index workspace when files are modified.

        This ensures the graph RAG index stays current for subsequent queries.
        Only triggers indexing once per file per session to avoid redundant work.
        """
        if file_path in self._indexed_files:
            return

        try:
            from tools.auto_index import auto_index_workspace

            result = auto_index_workspace.invoke({"workspace_path": WORKSPACE_PATH})
            self._indexed_files.add(file_path)
        except Exception:
            pass  # Silently ignore if graph RAG not configured

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Coder.\n"
            "\n"
            "YOUR JOB:\n"
            "  Write or edit code files exactly as instructed.\n"
            "  The Orchestrator has already analysed the codebase.\n"
            "  You have everything you need in the instruction.\n"
            "\n"
            "TOOLS YOU HAVE:\n"
            "  - read_file       — read a file before editing it\n"
            "  - write_file      — create a new file or replace entire file content\n"
            "  - edit_file       — replace one specific block inside a file\n"
            "  - run_test        — execute inline Python test code (see below)\n"
            "\n"
            "═══════════════════════════════════════════════════\n"
            "TESTING — when user asks to test code\n"
            "═══════════════════════════════════════════════════\n"
            "\n"
            "  When user asks to TEST something:\n"
            "    - Use run_test to execute inline Python test code\n"
            '    - Generate test code in python -c "..." style\n'
            "    - Test snippets run against workspace files\n"
            "    - Results are printed as logs with pass/fail status\n"
            "    - NEVER create any test files in the workspace\n"
            "    - NEVER use write_file for testing\n"
            "\n"
            "  CRITICAL: CLEAN UP AFTER TESTING\n"
            "    - run_test automatically cleans up its temp file\n"
            "    - If you accidentally created any files (like test_*.py), DELETE them\n"
            "    - Use edit_file to remove any files you created\n"
            "    - Workspace must be clean after testing - no test files allowed\n"
            "\n"
            "  CRITICAL IMPORT RULES:\n"
            "    - Workspace files are in: ./workspace/ directory\n"
            "    - Import paths are relative to workspace root\n"
            "    - If file is at: workspace/utils/math.py\n"
            "      import is: from utils.math import add\n"
            "    - NEVER use: from math import ... (that's Python stdlib)\n"
            "    - ALWAYS verify file location first with list_files\n"
            "\n"
            "  TEST GENERATION RULES:\n"
            "    - Generate simple test snippets in python -c style\n"
            '    - Format: run_test(code="...", imports="from utils.math import func")\n'
            "    - Test code should print results with clear pass/fail indicators\n"
            "    - Example test format:\n"
            '        code="""\n'
            "result = add(1, 2)\n"
            "print(f'1 + 2 = {result} | expected 3 ->', 'PASS' if result == 3 else 'FAIL')\n"
            "result = add(10, 5)\n"
            "print(f'10 + 5 = {result} | expected 15 ->', 'PASS' if result == 15 else 'FAIL')\n"
            '"""\n'
            "    - Test snippets are TEMPORARY files deleted after execution\n"
            "    - ALWAYS run tests AFTER making changes to verify correctness\n"
            "\n"
            "═══════════════════════════════════════════════════"
            "\n"
            "CHOOSING THE RIGHT TOOL — read this carefully\n"
            "═══════════════════════════════════════════════════\n"
            "\n"
            "  USE write_file WHEN:\n"
            "    - Creating a new file that does not exist yet\n"
            "    - The task touches more than 3 separate locations in the file\n"
            "    - The task is a whole-file transformation:\n"
            "        removing all comments, reformatting, renaming throughout\n"
            "    - PROCESS:\n"
            "        1. Call read_file to get the full current content\n"
            "        2. Apply ALL changes to the content in your head\n"
            "        3. Call write_file ONCE with the complete new content\n"
            "        4. Call read_file again to verify the result\n"
            "\n"
            "  USE edit_file WHEN:\n"
            "    - Changing ONE specific block or function\n"
            "    - Adding ONE new function or class\n"
            "    - Fixing ONE specific bug\n"
            "    - PROCESS:\n"
            "        1. Call read_file to get the exact current content\n"
            "        2. Copy the exact block verbatim from the file output\n"
            "        3. Call edit_file ONCE with that exact copied block\n"
            "        4. Call read_file again to verify the change landed\n"
            "\n"
            "  NEVER call edit_file more than 3 times on the same file.\n"
            "  If edit_file fails twice — switch to write_file approach.\n"
            "  NEVER guess old_content from memory — always read first.\n"
            "\n"
            "═══════════════════════════════════════════════════"
            "\n"
            "PATH RESOLUTION — ALWAYS VERIFY PATHS BEFORE EDITING\n"
            "═══════════════════════════════════════════════════\n"
            "\n"
            "  BEFORE calling edit_file or write_file:\n"
            "\n"
            "  1. CALL list_files TO SEE WHAT FILES EXIST\n"
            "     - This shows you all available files in the workspace\n"
            "     - Use this to find the correct filename\n"
            "\n"
            "  2. IF YOU HAVE A PATH BUT AREN'T SURE IT'S CORRECT:\n"
            "     - Try reading with different path variations\n"
            "     - Common wrong: M8/workspace/file.py, workspace/file.py\n"
            "     - Correct: just the filename like file.py\n"
            "\n"
            "  3. USE graph_code_search TO FIND FILES BY NAME\n"
            "     - Search for the filename to get the correct path\n"
            "\n"
            "  4. ONLY AFTER CONFIRMING THE PATH EXISTS:\n"
            "     - Call edit_file with the verified correct path\n"
            "\n"
            "  EXAMPLE WORKFLOW:\n"
            "    - Instruction says: edit 'M8/workspace/math_utils.py'\n"
            "    - You're not sure this path is correct\n"
            "    - STEP 1: Call list_files() → see ['math_utils.py', 'data_structures.py', ...]\n"
            "    - STEP 2: Identify correct name is 'math_utils.py'\n"
            "    - STEP 3: Call read_file('math_utils.py') → verify it exists\n"
            "    - STEP 4: Now call edit_file('math_utils.py', ...)\n"
            "\n"
            "  NEVER assume a path is correct — ALWAYS verify first.\n"
            "\n"
            "═══════════════════════════════════════════════════"
            "\n"
            "VERIFICATION — mandatory after every write or edit\n"
            "═══════════════════════════════════════════════════\n"
            "  After every write_file or edit_file call:\n"
            "    1. Call read_file on the same file\n"
            "    2. Confirm the change is present\n"
            "    3. Confirm nothing else was accidentally removed\n"
            "    4. Only report CHANGES: after verification passes\n"
            "\n"
            "  If verification fails:\n"
            "    - Report exactly what is wrong\n"
            "    - Retry once with corrected content\n"
            "    - If second attempt also fails — report failure clearly\n"
            "\n"
            "RULES:\n"
            "  - NEVER ask for more context\n"
            "  - NEVER run code or tests manually\n"
            "  - Write complete working code — no placeholders or TODOs\n"
            "  - Follow the coding style in the instruction exactly\n"
            "\n"
            "FINAL RESPONSE:\n"
            "  CHANGES:\n"
            "  - created: path/to/file.py\n"
            "  - edited:  path/to/other.py\n"
            "  \n"
            "  TESTS:\n"
            "  - test output logs here"
        )

    @property
    def tools(self) -> List[Any]:
        return CODER_TOOLS

    def build_todos(self, task: Task) -> TodoList:
        todos = TodoList()
        instruction = task["instruction"].lower()

        file_pattern = re.compile(r"[\w/]+\.\w{1,5}")
        files_mentioned = file_pattern.findall(task["instruction"])

        if files_mentioned:
            seen = set()
            for f in files_mentioned:
                if f not in seen:
                    seen.add(f)
                    action = (
                        "edit"
                        if any(
                            w in instruction
                            for w in ["edit", "update", "fix", "change", "modify"]
                        )
                        else "write"
                    )
                    todos.add(f"{action} {f}")
        else:
            if any(
                w in instruction
                for w in ["create", "add", "implement", "write", "build"]
            ):
                todos.add("write the required files")
            if any(
                w in instruction for w in ["edit", "update", "fix", "change", "modify"]
            ):
                todos.add("edit the required files")
            if not todos.items:
                todos.add("implement the requested changes")

        if any(w in instruction for w in ["test", "verify", "check"]):
            todos.add("run tests using run_test tool")

        todos.add("confirm all files written in CHANGES: section")
        return todos

    def run(self, task: Task) -> TaskResult:
        # Auto-index workspace at start of coding task (incremental, skips unchanged files)
        try:
            from tools.auto_index import auto_index_workspace

            auto_index_workspace.invoke({"workspace_path": WORKSPACE_PATH})
        except Exception:
            pass  # Silently ignore if graph RAG not configured

        result = super().run(task)
        artifacts = self._extract_artifacts(result["output"])

        # Auto-index after files are modified (keeps graph current for subsequent queries)
        for file_path in artifacts:
            self._ensure_indexed(file_path)

        # Cleanup: remove any test files created during testing
        self._cleanup_test_files()

        return TaskResult(
            task=result["task"],
            output=result["output"],
            success=result["success"],
        )

    def _cleanup_test_files(self) -> None:
        """Clean up any test files in workspace after testing."""
        try:
            import os
            import glob

            workspace = os.path.abspath(WORKSPACE_PATH)

            test_files = glob.glob(os.path.join(workspace, "test_*.py"))
            test_files += glob.glob(os.path.join(workspace, "*_test.py"))

            for test_file in test_files:
                try:
                    os.remove(test_file)
                    print(f"[CLEANUP] Removed test file: {test_file}")
                except Exception:
                    pass

            app_log = os.path.join(workspace, "app.log")
            if os.path.exists(app_log):
                try:
                    os.remove(app_log)
                    print(f"[CLEANUP] Removed app.log")
                except Exception:
                    pass
        except Exception:
            pass

    def _extract_artifacts(self, output: str) -> List[str]:
        artifacts = []
        pattern = re.compile(
            r"-\s+(?:created|edited|wrote|modified|updated):\s*(\S+)", re.IGNORECASE
        )
        ok_pattern = re.compile(r"OK:\s+wrote\s+(\S+)")

        for match in pattern.finditer(output):
            artifacts.append(match.group(1))

        for match in ok_pattern.finditer(output):
            path = match.group(1)
            if path not in artifacts:
                artifacts.append(path)

        return artifacts
