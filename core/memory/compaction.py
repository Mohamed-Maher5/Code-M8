# core/memory/compaction.py
# Multi-level memory compaction system

from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import json

from core.memory.llm_extractor import (
    compact_turns_with_llm,
    create_compaction_schedule,
)


class CompactionManager:
    """
    Manages memory compaction across multiple levels.

    Level 0: Raw turns (last 4 turns kept as-is)
    Level 1: First compaction (turns 5-20 → 1 summary)
    Level 2: Second compaction (turns 21-100 → 1 summary)
    Level 3: Third compaction (turns 100+ → 1 summary)
    """

    def __init__(self, sessions_path: str = "sessions"):
        self.sessions_path = Path(sessions_path)
        self._compaction_cache: Dict[str, Dict[int, Dict]] = {}

    def get_compacted_memory(
        self,
        llm: Any,
        session_id: str,
    ) -> Dict[str, Any]:
        """
        Get fully compacted memory for a session.

        Bug 2 Fix: Added caching to avoid calling LLM on every call.

        Returns:
            {
                "recent_turns": [...],  # Last 4 turns detailed
                "compaction_level_1": {...},  # Turns 5-20 summarized
                "compaction_level_2": {...},  # Turns 21-100 summarized
                "compaction_level_3": {...},  # Turns 100+ summarized
                "all_files": [...],
                "all_problems": [...],
                "all_solutions": [...],
            }
        """
        session_file = self.sessions_path / f"{session_id}.json"

        if not session_file.exists():
            return self._empty_compacted_memory()

        try:
            turns = json.loads(session_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[COMPACTION] Failed to load session: {e}")
            return self._empty_compacted_memory()

        total_turns = len(turns)

        if total_turns == 0:
            return self._empty_compacted_memory()

        # Bug 2 Fix: Check cache before computing
        cache_key = f"{session_id}:{total_turns}"
        if cache_key in self._compaction_cache:
            cached = self._compaction_cache[cache_key]
            # Still update recent_turns with latest data
            cached["recent_turns"] = turns[-4:]
            return cached

        # Split turns by compaction level
        recent = turns[-4:] if total_turns >= 1 else []
        level1_turns = turns[4:20] if total_turns > 4 else []
        level2_turns = turns[20:100] if total_turns > 20 else []
        level3_turns = turns[100:] if total_turns > 100 else []

        result = {
            "recent_turns": recent,
            "compaction_level_1": None,
            "compaction_level_2": None,
            "compaction_level_3": None,
            "all_files": self._collect_files(turns),
            "all_problems": self._collect_problems(turns),
            "all_solutions": self._collect_solutions(turns),
            "total_turns": total_turns,
        }

        # Compact each level using LLM
        if level1_turns:
            result["compaction_level_1"] = compact_turns_with_llm(llm, level1_turns)
            print(f"[COMPACTION] Level 1: {len(level1_turns)} turns → 1 summary")

        if level2_turns:
            result["compaction_level_2"] = compact_turns_with_llm(llm, level2_turns)
            print(f"[COMPACTION] Level 2: {len(level2_turns)} turns → 1 summary")

        if level3_turns:
            result["compaction_level_3"] = compact_turns_with_llm(llm, level3_turns)
            print(f"[COMPACTION] Level 3: {len(level3_turns)} turns → 1 summary")

        # Bug 2 Fix: Cache the result
        self._compaction_cache[cache_key] = result

        return result

    def get_memory_for_planning(
        self,
        llm: Any,
        session_id: str,
    ) -> str:
        """
        Get formatted memory string for orchestrator planning.

        This is what gets passed to the orchestrator to understand
        what has been done in the session.
        """
        compacted = self.get_compacted_memory(llm, session_id)

        lines = ["=== SESSION MEMORY ==="]

        # Add recent turns
        recent = compacted.get("recent_turns", [])
        if recent:
            lines.append("\n## Recent Turns (detailed):")
            for turn in recent[-4:]:
                turn_id = turn.get("turn_id", "???")
                user = turn.get("user_message", "")[:100]
                files = turn.get("files_mentioned", [])
                files_str = f" [files: {', '.join(files)}]" if files else ""
                lines.append(f"- T{turn_id}: {user}{files_str}")

        # Add level 1 compaction
        l1 = compacted.get("compaction_level_1")
        if l1:
            lines.append(f"\n## Earlier ({l1.get('turn_count', 0)} turns):")
            lines.append(f"  {l1.get('summary', '')}")
            if l1.get("key_files"):
                lines.append(f"  Files: {', '.join(l1['key_files'][:5])}")

        # Add level 2 compaction
        l2 = compacted.get("compaction_level_2")
        if l2:
            lines.append(f"\n## Earlier Session ({l2.get('turn_count', 0)} turns):")
            lines.append(f"  {l2.get('summary', '')}")

        # Add level 3 compaction
        l3 = compacted.get("compaction_level_3")
        if l3:
            lines.append(f"\n## Session Start ({l3.get('turn_count', 0)} turns):")
            lines.append(f"  {l3.get('summary', '')}")

        # Add all problems/solutions
        problems = compacted.get("all_problems", [])
        solutions = compacted.get("all_solutions", [])

        if problems:
            lines.append(f"\n## Problems Solved:")
            for p in problems[:5]:
                lines.append(f"  - {p}")

        if solutions:
            lines.append(f"\n## Solutions Applied:")
            for s in solutions[:5]:
                lines.append(f"  - {s}")

        lines.append("=== END MEMORY ===")

        return "\n".join(lines)

    def _empty_compacted_memory(self) -> Dict[str, Any]:
        return {
            "recent_turns": [],
            "compaction_level_1": None,
            "compaction_level_2": None,
            "compaction_level_3": None,
            "all_files": [],
            "all_problems": [],
            "all_solutions": [],
            "total_turns": 0,
        }

    def _collect_files(self, turns: List[Dict]) -> List[str]:
        files = set()
        for turn in turns:
            files.update(turn.get("files_mentioned", []))
            mem = turn.get("memory", {})
            entities = mem.get("entities", {})
            files.update(entities.get("files", []))
        return sorted(list(files))

    def _collect_problems(self, turns: List[Dict]) -> List[str]:
        problems = set()
        for turn in turns:
            mem = turn.get("memory", {})
            knowledge = mem.get("knowledge", {})
            problems.update(knowledge.get("problems_found", []))
        return sorted(list(problems))

    def _collect_solutions(self, turns: List[Dict]) -> List[str]:
        solutions = set()
        for turn in turns:
            mem = turn.get("memory", {})
            knowledge = mem.get("knowledge", {})
            solutions.update(knowledge.get("solutions_applied", []))
        return sorted(list(solutions))


# Global instance
_compaction_manager: Optional[CompactionManager] = None


def get_compaction_manager() -> CompactionManager:
    global _compaction_manager
    if _compaction_manager is None:
        from core.config import SESSIONS_PATH

        _compaction_manager = CompactionManager(sessions_path=SESSIONS_PATH)
    return _compaction_manager
