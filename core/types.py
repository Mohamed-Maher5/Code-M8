# from typing import TypedDict, List

# class Task(TypedDict):
#     agent: str           # "explorer" or "coder"
#     instruction: str     # what to do
#     context: str         # filled by dispatcher with previous results

# class TaskResult(TypedDict):
#     task: Task           # the original task
#     output: str          # what the agent produced
#     success: bool        # did it work or not

# class Message(TypedDict):
#     role: str            # "user" or "assistant"
#     content: str         # the message text
#     timestamp: str       # when it was sent

# class Plan(TypedDict):
#     steps: List[Task]    # ordered list of tasks to execute


"""
types.py
========
Shared types for the entire project.
Uses TypedDict for simple, readable definitions.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict


# ══════════════════════════════════════════════════════════════════════════════
# ENUMS
# ══════════════════════════════════════════════════════════════════════════════

class AgentName(str, Enum):
    ORCHESTRATOR = "orchestrator"
    EXPLORER     = "explorer"
    CODER        = "coder"
    RUNNER       = "runner"


class TaskStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    SKIPPED   = "skipped"


class Language(str, Enum):
    PYTHON     = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO         = "go"
    RUBY       = "ruby"
    SHELL      = "shell"
    UNKNOWN    = "unknown"


# ══════════════════════════════════════════════════════════════════════════════
# CORE TYPES  (TypedDict — simple and readable)
# ══════════════════════════════════════════════════════════════════════════════

class Message(TypedDict):
    role:      str   # "user" or "assistant"
    content:   str   # the message text
    timestamp: str   # when it was sent


class Task(TypedDict):
    agent:       str   # "explorer" or "coder"
    instruction: str   # what to do
    context:     str   # filled by dispatcher with previous results


class TaskResult(TypedDict):
    task:    Task   # the original task
    output:  str    # what the agent produced
    success: bool   # did it work or not


class Plan(TypedDict):
    steps: List[Task]   # ordered list of tasks to execute


# ══════════════════════════════════════════════════════════════════════════════
# EXTENDED TYPES  (used internally by agents and tools)
# ══════════════════════════════════════════════════════════════════════════════

class ToolResult(TypedDict):
    call_id:     str
    tool_name:   str
    output:      str
    error:       Optional[str]
    success:     bool
    duration_ms: int


class TestReport(TypedDict):
    passed:       bool
    stdout:       str
    stderr:       str
    errors:       Optional[str]
    files_tested: List[str]
    command_used: str
    duration_ms:  int
    attempt:      int


class RetrySignal(TypedDict):
    original_plan:  Plan
    failed_report:  TestReport
    coder_output:   TaskResult
    attempt_number: int
    max_retries:    int


class SandboxResult(TypedDict):
    stdout:       str
    stderr:       str
    exit_code:    int
    timed_out:    bool
    oom_killed:   bool
    wall_time_ms: int


class Session(TypedDict):
    session_id:     str
    workspace_path: str
    messages:       List[Message]
    created_at:     float
    updated_at:     float


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS  (functions that create typed dicts with defaults filled in)
# ══════════════════════════════════════════════════════════════════════════════

def make_task(
    agent:       str,
    instruction: str,
    context:     str = "",
) -> Task:
    return Task(agent=agent, instruction=instruction, context=context)


def make_task_result(
    task:    Task,
    output:  str,
    success: bool = True,
) -> TaskResult:
    return TaskResult(task=task, output=output, success=success)


def make_message(role: str, content: str) -> Message:
    return Message(
        role      = role,
        content   = content,
        timestamp = str(time.time()),
    )


def make_session(workspace_path: str = "") -> Session:
    return Session(
        session_id     = uuid.uuid4().hex[:8],
        workspace_path = workspace_path,
        messages       = [],
        created_at     = time.time(),
        updated_at     = time.time(),
    )


def make_sandbox_result(
    stdout:    str  = "",
    stderr:    str  = "",
    exit_code: int  = 0,
    timed_out: bool = False,
    oom_killed: bool = False,
    wall_time_ms: int = 0,
) -> SandboxResult:
    return SandboxResult(
        stdout       = stdout,
        stderr       = stderr,
        exit_code    = exit_code,
        timed_out    = timed_out,
        oom_killed   = oom_killed,
        wall_time_ms = wall_time_ms,
    )


def sandbox_success(result: SandboxResult) -> bool:
    return (
        result["exit_code"] == 0
        and not result["timed_out"]
        and not result["oom_killed"]
    )


def sandbox_failure_reason(result: SandboxResult) -> Optional[str]:
    if result["timed_out"]:
        return "Execution timed out"
    if result["oom_killed"]:
        return "Out of memory"
    if result["exit_code"] != 0:
        return result["stderr"].strip() or f"Exit code {result['exit_code']}"
    return None


# ══════════════════════════════════════════════════════════════════════════════
# EXCEPTIONS
# ══════════════════════════════════════════════════════════════════════════════

class RoutingViolation(Exception):
    """Raised by dispatcher when an illegal agent-to-agent route is attempted."""
    def __init__(self, source: str, destination: str, reason: str = ""):
        self.source      = source
        self.destination = destination
        super().__init__(f"Routing violation: {source} → {destination}. {reason}")


class PlanViolation(Exception):
    """Raised by planner when the plan breaks ordering rules."""
    pass


class SandboxError(Exception):
    """Raised when Docker itself fails (not when sandboxed code fails)."""
    pass


# ── Helpers ───────────────────────────────────────────────────────────────────
 
def make_task(agent: str, instruction: str, context: str = "") -> Task:
    return Task(agent=agent, instruction=instruction, context=context)
 
 
def make_task_result(task: Task, output: str, success: bool = True) -> TaskResult:
    return TaskResult(task=task, output=output, success=success)
 