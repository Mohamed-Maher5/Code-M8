# core/types.py

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import List, Optional, TypedDict


# ── Enums ─────────────────────────────────────────────────────────────────────

class AgentName(str, Enum):
    ORCHESTRATOR = "orchestrator"
    EXPLORER     = "explorer"
    CODER        = "coder"


class TaskStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    SKIPPED   = "skipped"


# ── Core Types ────────────────────────────────────────────────────────────────

class Message(TypedDict):
    role     : str   # "user" | "assistant"
    content  : str
    timestamp: str

class Task(TypedDict):
    agent      : str   # "orchestrator" | "explorer" | "coder"
    instruction: str
    context    : str   # filled by dispatcher with previous results

class TaskResult(TypedDict):
    task   : Task
    output : str
    success: bool

class Plan(TypedDict):
    steps: List[Task]

class AgentResponse(TypedDict):
    agent  : str
    content: str
    success: bool

class Session(TypedDict):
    session_id    : str
    workspace_path: str
    messages      : List[Message]
    created_at    : float
    updated_at    : float


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_task(agent: str, instruction: str, context: str = "") -> Task:
    return Task(agent=agent, instruction=instruction, context=context)

def make_task_result(task: Task, output: str, success: bool = True) -> TaskResult:
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

class RoutingViolation(Exception):
    """Raised by dispatcher when an illegal agent route is attempted."""
    def __init__(self, source: str, destination: str, reason: str = ""):
        self.source      = source
        self.destination = destination
        super().__init__(f"Routing violation: {source} → {destination}. {reason}")