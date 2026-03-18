"""
dispatcher.py
=============
Routes each Task to the correct agent and enforces routing rules.

Rules:
    Explorer result  → Orchestrator ONLY
    Coder input      → Orchestrator digest ONLY
    Runner input     → Coder artifacts ONLY
    Runner = None    → skipped silently, no error
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

try:
    from typing import Protocol, runtime_checkable
except ImportError:
    from typing_extensions import Protocol, runtime_checkable

from core.types import (
    Plan,
    RoutingViolation,
    Task,
    TaskResult,
    make_task,
    make_task_result,
)


# ── Protocols ─────────────────────────────────────────────────────────────────

@runtime_checkable
class Agent(Protocol):
    def run(self, task: Task) -> TaskResult:
        ...


@runtime_checkable
class OrchestratorAgent(Protocol):
    def run(self, task: Task) -> TaskResult:
        ...
    def digest(self, explorer_result: TaskResult, original_request: str) -> str:
        ...
    def plan(self, user_request: str, session_history: List[str]) -> Plan:
        ...
    def summarize(self, user_request: str, all_results: List[TaskResult], tests_passed: bool) -> str:
        ...


# ── Helpers ───────────────────────────────────────────────────────────────────

def _set_status(agent: str, action: str) -> None:
    """Update shared status — icon in terminal_ui updates live."""
    try:
        from core.agent_status import set_agent
        set_agent(agent, action)
    except ImportError:
        pass


# ── Dispatcher ────────────────────────────────────────────────────────────────

class Dispatcher:

    def __init__(
        self,
        orchestrator: OrchestratorAgent,
        explorer:     Agent,
        coder:        Agent,
        test_runner:  Optional[Agent] = None,
    ) -> None:
        self._agents: dict[str, Optional[Agent]] = {
            "orchestrator": orchestrator,  # type: ignore[dict-item]
            "explorer":     explorer,
            "coder":        coder,
            "runner":       test_runner,
        }

    def run_plan(
        self,
        plan:         Plan,
        orchestrator: OrchestratorAgent,
        user_request: str = "",
    ) -> List[TaskResult]:
        """
        Executes every step in the Plan.
        Updates agent_status before every LLM call so
        the terminal spinner shows the correct icon.
        """
        all_results:     List[TaskResult]    = []
        explorer_result: Optional[TaskResult] = None
        coder_result:    Optional[TaskResult] = None

        for task in plan["steps"]:
            agent_name = task["agent"]

            # ── EXPLORER ──────────────────────────────────────────────────────
            if agent_name == "explorer":
                result          = self._route(task, "explorer")
                explorer_result = result
                all_results.append(result)

            # ── CODER ─────────────────────────────────────────────────────────
            elif agent_name == "coder":
                if explorer_result is not None:
                    # Orchestrator digests Explorer output → show brain icon
                    _set_status("orchestrator", "digesting findings")

                    digested = orchestrator.digest(
                        explorer_result  = explorer_result,
                        original_request = user_request or task["instruction"],
                    )
                    coder_task = make_task(
                        agent       = "coder",
                        instruction = digested,
                        context     = "",
                    )
                else:
                    coder_task = task

                result       = self._route(coder_task, "coder")
                coder_result = result
                all_results.append(result)

            # ── RUNNER ────────────────────────────────────────────────────────
            elif agent_name == "runner":
                # Not registered — skip silently
                if self._agents.get("runner") is None:
                    continue

                if coder_result is not None:
                    runner_task = make_task(
                        agent       = "runner",
                        instruction = task["instruction"],
                        context     = coder_result["output"],
                    )
                    result = self._route(runner_task, "runner")
                else:
                    result = make_task_result(
                        task    = task,
                        output  = "No code written. Skipping tests.",
                        success = True,
                    )
                all_results.append(result)

            else:
                raise RoutingViolation(
                    source      = agent_name,
                    destination = "unknown",
                    reason      = f"Unknown agent '{agent_name}' in plan.",
                )

        return all_results

    def route(self, task: Task) -> TaskResult:
        return self._route(task, task["agent"])

    def agents_ready(self) -> bool:
        return all(
            self._agents.get(k) is not None
            for k in ("explorer", "coder")
        )

    def _route(self, task: Task, agent_name: str) -> TaskResult:
        agent: Optional[Agent] = self._agents.get(agent_name)  # type: ignore
        if agent is None:
            raise RoutingViolation(
                source      = "dispatcher",
                destination = agent_name,
                reason      = f"No agent registered for '{agent_name}'.",
            )
        # Update status so terminal_ui spinner shows correct icon
        _set_status(agent_name, {
            "explorer": "reading files",
            "coder":    "writing code",
            "runner":   "running tests",
        }.get(agent_name, "thinking"))

        return agent.run(task)