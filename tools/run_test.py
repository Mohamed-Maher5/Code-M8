# tools/run_test.py
# Execute inline Python test scripts and capture results
# Used by: Coder agent

from __future__ import annotations

import os
import re
import subprocess
from typing import Any, Dict

from langchain_core.tools import tool

from core.config import WORKSPACE_PATH
from utils.logger import logger


TEMP_TEST_FILE = "_test_runner_temp.py"


@tool
def run_test(code: str, imports: str = "") -> str:
    """Execute inline Python test code and return results.

    Args:
        code: Python test code to execute (e.g., "result = add(1, 2); print(f'Result: {result}')")
        imports: Optional imports needed (e.g., "from utils.math import add")

    Returns:
        Formatted test output with success/failure status.
        Includes test results, logs, and any errors.
    """
    logger.info(f"Running test with code: {code[:100]}...")

    workspace = os.path.abspath(WORKSPACE_PATH)
    project_root = os.path.dirname(workspace)
    temp_path = os.path.join(workspace, TEMP_TEST_FILE)

    def _resolve_imports(imports: str, workspace: str) -> str:
        """Resolve imports to work with workspace files."""
        if not imports:
            return imports

        import_lines = []

        # Get all .py files in workspace (without .py extension)
        workspace_files = []
        if os.path.exists(workspace):
            for f in os.listdir(workspace):
                if f.endswith(".py") and not f.startswith("_") and f != "__init__.py":
                    workspace_files.append(f[:-3])  # remove .py

        for line in imports.split("\n"):
            if not line.strip():
                continue

            # Handle utils.* imports
            if "from utils." in line or "from utils import" in line:
                if not os.path.exists(os.path.join(workspace, "utils")):
                    new_line = line.replace("from utils.", "from ")
                    new_line = new_line.replace("from utils import", "import")
                    import_lines.append(new_line)
                    continue

            # Handle workspace files that conflict with stdlib (math, json, etc.)
            import_match = re.match(r"from\s+(\w+)\s+import", line)
            if import_match:
                module_name = import_match.group(1)
                # Check if this is a workspace file (not stdlib)
                if module_name in workspace_files or os.path.exists(
                    os.path.join(workspace, f"{module_name}.py")
                ):
                    # Add sys.path first, then import
                    import_lines.append("import sys")
                    import_lines.append(f"sys.path.insert(0, r'{workspace}')")
                    # Keep original import
                    import_lines.append(line)
                    continue

            import_lines.append(line)

        return "\n".join(import_lines)

    resolved_imports = _resolve_imports(imports, workspace)
    full_script = f"{resolved_imports}\n{code}" if resolved_imports else code

    try:
        with open(temp_path, "w") as f:
            f.write(full_script)

        print(f"\n{'=' * 60}")
        print("=== Running Tests ===")
        print("=" * 60)
        print("\n--- Test Script ---")
        print(full_script)
        print("--- End Script ---\n")

        result = subprocess.run(
            ["python", temp_path],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=workspace,
        )

        output = result.stdout.strip()
        error = result.stderr.strip()

        print("\n--- Test Results ---")
        if output:
            print(output)
        if error:
            print("Errors:", error)
        print("--- End Results ---\n")

        if result.returncode != 0:
            logger.error(f"Test failed: {error}")
            return _format_failure(output, error)

        logger.info(f"Test passed: {output}")
        return _format_success(output)

    except subprocess.TimeoutExpired:
        logger.error("Test timed out")
        return "❌ Test timed out after 30 seconds"
    except Exception as e:
        logger.error(f"Test error: {e}")
        return f"❌ Error: {str(e)}"
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def _format_success(output: str) -> str:
    """Format successful test output."""
    lines = []
    if output:
        lines.append(output)
    lines.append("")
    lines.append("✅ All tests passed!")
    return "\n".join(lines)


def _format_failure(output: str, error: str) -> str:
    """Format failed test output."""
    lines = ["❌ Test Failed", ""]
    if output:
        lines.append(output)
    if error:
        lines.append("")
        lines.append("=== Error ===")
        lines.append(error)
    return "\n".join(lines)
