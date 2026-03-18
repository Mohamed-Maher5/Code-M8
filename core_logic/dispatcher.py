# core_logic/dispatcher.py
# Routes each Task to the correct agent and enforces routing rules
#
# Rules:
#     Explorer result → Orchestrator digest ONLY before Coder
#     Coder input     → Orchestrator digest ONLY
#     Runner          → skipped silently until TestRunner is built

from __future__ import annotations

from typing import List, Optional

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
from utils.logger import logger


# ── Protocols ─────────────────────────────────────────────────────────────────

@runtime_checkable
class Agent(Protocol):
    def run(self, task: Task) -> TaskResult: ...


@runtime_checkable
class OrchestratorAgent(Protocol):
    def run(self, task: Task) -> TaskResult: ...
    def digest(self, explorer_result: TaskResult, original_request: str) -> str: ...
    def plan(self, user_request: str, session_history: List[str]) -> Plan: ...
    def summarize(self, user_request: str, all_results: List[TaskResult], tests_passed: bool) -> str: ...


# ── Helpers ───────────────────────────────────────────────────────────────────

def _set_status(agent: str, action: str) -> None:
    # update shared status — silently fails if agent_status not built yet
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
        explorer    : Agent,
        coder       : Agent,
        test_runner : Optional[Agent] = None,
    ) -> None:
        self._agents: dict[str, Optional[Agent]] = {
            "orchestrator": orchestrator,  # type: ignore[dict-item]
            "explorer"    : explorer,
            "coder"       : coder,
            "runner"      : test_runner,   # None until Task 3
        }

    def run_plan(
        self,
        plan        : Plan,
        orchestrator: OrchestratorAgent,
        user_request: str = "",
    ) -> List[TaskResult]:
        """
        Executes every step in the Plan in order.
        Explorer → Orchestrator digest → Coder → Runner (skipped for now)
        """
        all_results    : List[TaskResult]     = []
        explorer_result: Optional[TaskResult] = None
        coder_result   : Optional[TaskResult] = None

        for task in plan["steps"]:
            agent_name = task["agent"]

            # ── Explorer ──────────────────────────────────────────────────────
            if agent_name == "explorer":
                logger.info("Dispatcher: running explorer")
                result          = self._route(task, "explorer")
                explorer_result = result
                all_results.append(result)

            # ── Coder ─────────────────────────────────────────────────────────
            elif agent_name == "coder":
                if explorer_result is not None:
                    # orchestrator digests explorer output before coder sees it
                    _set_status("orchestrator", "digesting findings")
                    logger.info("Dispatcher: orchestrator digesting explorer output")

                    digested  = orchestrator.digest(
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

                logger.info("Dispatcher: running coder")
                result       = self._route(coder_task, "coder")
                coder_result = result
                all_results.append(result)

            # ── Runner — skipped until Task 3 ─────────────────────────────────
            elif agent_name == "runner":
                if self._agents.get("runner") is None:
                    logger.info("Dispatcher: runner not registered — skipping")
                    continue

                runner_task = make_task(
                    agent       = "runner",
                    instruction = task["instruction"],
                    context     = coder_result["output"] if coder_result else "",
                )
                result = self._route(runner_task, "runner")
                all_results.append(result)

            else:
                raise RoutingViolation(
                    source      = agent_name,
                    destination = "unknown",
                    reason      = f"Unknown agent '{agent_name}' in plan.",
                )

        return all_results

    def route(self, task: Task) -> TaskResult:
        # public single-task route — used by loop for direct calls
        return self._route(task, task["agent"])

    def agents_ready(self) -> bool:
        # check minimum required agents are registered
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

        _set_status(agent_name, {
            "explorer": "reading files",
            "coder"   : "writing code",
            "runner"  : "running tests",
        }.get(agent_name, "thinking"))

        logger.info(f"Dispatcher: routing to {agent_name}")
        return agent.run(task)