"""
Context Injector — proactively fills the token budget with the most
relevant memory before every LLM call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

try:
    from core.token_usage import estimate_tokens
except ImportError:

    def estimate_tokens(text: str) -> int:
        return len(text) // 4


try:
    from utils.logger import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


@dataclass
class MemoryContext:
    project_facts: str = ""
    session_summary: str = ""
    hot_entities: str = ""
    vector_hits: str = ""
    graph_hits: str = ""
    raw_history: str = ""

    def render(self) -> str:
        """Render all non-empty sections as a single injected block."""
        parts: list[str] = []
        if self.project_facts:
            parts.append(f"### Project facts\n{self.project_facts}")
        if self.session_summary:
            parts.append(f"### Session summary\n{self.session_summary}")
        if self.hot_entities:
            parts.append(f"### Recently touched\n{self.hot_entities}")
        if self.vector_hits:
            parts.append(f"### Relevant context\n{self.vector_hits}")
        if self.raw_history:
            parts.append(f"### Recent turns\n{self.raw_history}")
        return "\n\n".join(parts)

    def token_count(self) -> int:
        return estimate_tokens(self.render())


class ContextInjector:
    DEFAULT_BUDGET = {
        "project_facts": 0.10,
        "session_summary": 0.15,
        "hot_entities": 0.10,
        "vector_results": 0.35,
        "graph_results": 0.00,
        "raw_history": 0.30,
    }

    def __init__(self, total_tokens: int = 4000):
        self.total_tokens = total_tokens

    def build(self, query: str, session_id: str) -> MemoryContext:
        ctx = MemoryContext()
        alloc = self._allocate()

        # ── project facts ─────────────────────────────────────────────────────
        try:
            from core.memory.project_memory import get_project_memory

            ctx.project_facts = get_project_memory().render_for_context(
                token_budget=alloc["project_facts"]
            )
        except Exception as e:
            logger.debug(f"ContextInjector: project_facts failed: {e}")

        # ── session summary (compacted older turns) ────────────────────────────
        try:
            from core.session_manager import build_compact_memory

            mem = build_compact_memory(
                recent_turns=2, max_total_chars=alloc["session_summary"] * 4
            )
            ctx.session_summary = mem.get("rolling_summary", "")
        except Exception as e:
            logger.debug(f"ContextInjector: session_summary failed: {e}")

        # ── hot entities (recently touched files) ─────────────────────────────
        try:
            from core.session_manager import build_compact_memory

            mem = build_compact_memory(recent_turns=2)
            files = mem.get("files_mentioned", [])
            if files:
                ctx.hot_entities = "Files: " + ", ".join(files[:15])
        except Exception as e:
            logger.debug(f"ContextInjector: hot_entities failed: {e}")

        # ── vector search over conversation history ────────────────────────────
        try:
            from core.memory.vector_store import get_vector_store

            store = get_vector_store()
            if store.count() > 0:
                hits = store.mmr_search(query, top_k=4, diversity=0.4)
                snippets = []
                budget = alloc["vector_results"] * 4
                for hit in hits:
                    snippet = hit["text"][:300]
                    budget -= len(snippet)
                    if budget < 0:
                        break
                    snippets.append(snippet)
                ctx.vector_hits = "\n---\n".join(snippets)
        except Exception as e:
            logger.debug(f"ContextInjector: vector_results failed: {e}")

        # ── raw recent history ─────────────────────────────────────────────────
        try:
            from core.session_manager import load_history, _format_turn

            history = load_history(last_n=4, max_chars=300)
            ctx.raw_history = "\n".join(_format_turn(t) for t in history)
        except Exception as e:
            logger.debug(f"ContextInjector: raw_history failed: {e}")

        return ctx

    def _allocate(self) -> dict[str, int]:
        """Convert percentage budget to token counts."""
        return {k: int(self.total_tokens * v) for k, v in self.DEFAULT_BUDGET.items()}


_injector: Optional[ContextInjector] = None


def get_context_injector(total_tokens: int = 4000) -> ContextInjector:
    global _injector
    if _injector is None:
        _injector = ContextInjector(total_tokens=total_tokens)
    return _injector
