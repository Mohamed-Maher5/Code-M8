# core_logic/synthesizer.py
# Collects Explorer and Coder results → builds final answer
# Trims outputs before summarize to avoid slow huge prompts

from __future__ import annotations

from typing import TYPE_CHECKING, List

from core.types import TaskResult
from utils.logger import logger

if TYPE_CHECKING:
    from core_logic.dispatcher import OrchestratorAgent

MAX_OUTPUT_CHARS = 800


def _set_status(agent: str, action: str) -> None:
    try:
        from core.agent_status import set_agent
        set_agent(agent, action)
    except ImportError:
        pass


class Synthesizer:

    def __init__(self, orchestrator: "OrchestratorAgent") -> None:
        self.orchestrator = orchestrator

    def synthesize(
        self,
        user_request: str,
        all_results : List[TaskResult],
    ) -> str:
        results = all_results

        if not results:
            return "No results to show."

        explorer_results = [r for r in results if r["task"]["agent"] == "explorer"]
        coder_results    = [r for r in results if r["task"]["agent"] == "coder"]

        logger.info(
            f"Synthesizer: {len(explorer_results)} explorer, "
            f"{len(coder_results)} coder results"
        )

        trimmed = []
        for r in results:
            t           = dict(r)
            t["output"] = r["output"][:MAX_OUTPUT_CHARS]
            if len(r["output"]) > MAX_OUTPUT_CHARS:
                t["output"] += "\n... [trimmed]"
            trimmed.append(t)

        _set_status("orchestrator", "writing answer")

        try:
            response = self.orchestrator.summarize(
                user_request = user_request,
                all_results  = trimmed,
                tests_passed = True,
            )
            logger.info("Synthesizer: summarize() succeeded")
            return response
        except Exception as e:
            logger.error(f"Synthesizer: summarize() failed — {e}")
            return self._fallback(explorer_results, coder_results)

    def _fallback(
        self,
        explorer_results: List[TaskResult],
        coder_results   : List[TaskResult],
    ) -> str:
        parts = []
        for r in explorer_results + coder_results:
            out = r["output"].strip()
            if out:
                parts.append(out)
        return "\n\n---\n\n".join(parts) if parts else "Done."