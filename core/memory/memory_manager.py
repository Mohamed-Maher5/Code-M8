"""
MemoryManager — single entry point for all memory operations.
Used by loop.py for all read/write/inject calls.
"""

from __future__ import annotations

try:
    from utils.logger import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


class MemoryManager:
    def on_session_start(self, session_id: str) -> None:
        """Called once when session starts."""
        try:
            from core.memory.project_memory import get_project_memory

            pm = get_project_memory()
            facts = pm.render_for_context(token_budget=200)
            if facts:
                logger.info(f"ProjectMemory loaded: {pm.search('stack', 3)}")
        except Exception as e:
            logger.debug(f"MemoryManager.on_session_start: {e}")

    def build_context(self, query: str, session_id: str) -> str:
        """
        Build injected memory context for an LLM call.
        Returns a formatted string to prepend to the planning prompt.
        """
        try:
            from core.memory.context_injector import get_context_injector

            ctx = get_context_injector().build(query, session_id)
            return ctx.render()
        except Exception as e:
            logger.debug(f"MemoryManager.build_context: {e}")
            return ""

    def on_turn_end(
        self,
        user_message: str,
        final_answer: str,
        llm_memory: dict | None,
    ) -> None:
        """Called after every turn to persist memory."""
        try:
            from core.memory.memory_writer import get_memory_writer

            get_memory_writer().write_turn(user_message, final_answer, llm_memory)
        except Exception as e:
            logger.debug(f"MemoryManager.on_turn_end: {e}")

    def on_session_end(self) -> None:
        """Called when session ends. Consolidates memory."""
        try:
            self._consolidate()
        except Exception as e:
            logger.debug(f"MemoryManager.on_session_end: {e}")

    def _consolidate(self) -> None:
        """Dedup and prune project memory."""
        from core.memory.project_memory import get_project_memory

        pm = get_project_memory()
        removed = pm.dedup()
        if removed:
            logger.info(f"Memory consolidation: removed {removed} duplicate facts")
        pm.forget_old(max_facts=500)


_manager: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    global _manager
    if _manager is None:
        _manager = MemoryManager()
    return _manager
