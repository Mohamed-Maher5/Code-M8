# core_logic/synthesizer.py
# Collects Explorer and Coder results → builds final answer
# Trims outputs before summarize to avoid slow huge prompts

from __future__ import annotations

from typing import TYPE_CHECKING, List

from core.types import TaskResult
from utils.logger import logger

if TYPE_CHECKING:
    from core_logic.dispatcher import OrchestratorAgent

MAX_OUTPUT_CHARS = 100000


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
        all_results: List[TaskResult],
    ) -> str:
        print("\n" + "#" * 80)
        print("[SYNTH DEBUG] ══ Synthesizer.synthesize() START ══")
        print(
            f"  User request: {user_request[:80]}{'...' if len(user_request) > 80 else ''}"
        )
        print(f"  Total results: {len(all_results)}")

        results = all_results

        if not results:
            print("[SYNTH DEBUG] No results, returning 'No results to show.'")
            print("#" * 80 + "\n")
            return "No results to show."

        explorer_results = [r for r in results if r["task"]["agent"] == "explorer"]
        coder_results = [r for r in results if r["task"]["agent"] == "coder"]

        print(f"  Results breakdown:")
        print(f"    - Explorer results: {len(explorer_results)}")
        print(f"    - Coder results: {len(coder_results)}")

        total_output_chars = sum(len(r["output"]) for r in results)
        print(f"    - Total output chars: {total_output_chars}")
        print(f"    - MAX_OUTPUT_CHARS limit: {MAX_OUTPUT_CHARS}")

        logger.info(
            f"Synthesizer: {len(explorer_results)} explorer, "
            f"{len(coder_results)} coder results"
        )

        print(f"\n[SYNTH DEBUG] Trimming outputs (max {MAX_OUTPUT_CHARS} chars each):")
        trimmed = []
        for i, r in enumerate(results):
            t = dict(r)
            original_len = len(r["output"])
            t["output"] = r["output"][:MAX_OUTPUT_CHARS]
            was_trimmed = original_len > MAX_OUTPUT_CHARS
            if was_trimmed:
                t["output"] += "\n... [trimmed]"
            print(
                f"    Result {i + 1} [{r['task']['agent']}]: {original_len} -> {len(t['output'])} chars {'[TRIMMED]' if was_trimmed else ''}"
            )
            trimmed.append(t)

        total_trimmed = sum(len(t["output"]) for t in trimmed)
        print(f"  Total after trimming: {total_trimmed} chars")

        _set_status("orchestrator", "writing answer")

        try:
            print(f"\n[SYNTH DEBUG] Calling orchestrator.summarize()...")
            response = self.orchestrator.summarize(
                user_request=user_request,
                all_results=trimmed,
                tests_passed=True,
            )
            print(f"[SYNTH DEBUG] orchestrator.summarize() succeeded")
            print(f"[SYNTH DEBUG] Response: {len(response)} chars")
            logger.info("Synthesizer: summarize() succeeded")
            print("#" * 80 + "\n")
            return response
        except Exception as e:
            print(f"[SYNTH DEBUG] ERROR in summarize(): {e}")
            print(f"[SYNTH DEBUG] Falling back to _fallback()")
            logger.error(f"Synthesizer: summarize() failed — {e}")
            fallback_response = self._fallback(explorer_results, coder_results)
            print(f"[SYNTH DEBUG] Fallback response: {len(fallback_response)} chars")
            print("#" * 80 + "\n")
            return fallback_response

    def _fallback(
        self,
        explorer_results: List[TaskResult],
        coder_results: List[TaskResult],
    ) -> str:
        parts = []
        for r in explorer_results + coder_results:
            out = r["output"].strip()
            if out:
                parts.append(out)
        return "\n\n---\n\n".join(parts) if parts else "Done."
