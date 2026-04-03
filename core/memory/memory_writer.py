"""
Memory Writer — persists turn data to project memory and vector store.
Called once at the end of every turn.
"""

from __future__ import annotations

from typing import Optional

try:
    from utils.logger import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


_MEMORABLE_SECTIONS = {
    "language": "Stack",
    "framework": "Stack",
    "dependency": "Stack",
    "convention": "Conventions",
    "pattern": "Conventions",
    "error": "Known issues",
    "bug": "Known issues",
    "preference": "User preferences",
    "decision": "Key decisions",
}

# Expanded trigger keywords - more inclusive
_TRIGGER_KEYWORDS = {
    "always",
    "never",
    "prefer",
    "use",
    "stack",
    "framework",
    "pattern",
    "convention",
    "rule",
    "decided",
    "important",
    "remember",
    "note",
    "warning",
    "gotcha",
    "version",
    # Added more common patterns
    "add",
    "create",
    "fix",
    "implement",
    "update",
    "modify",
    "created",
    "added",
    "fixed",
    "implemented",
    "updated",
}


class MemoryWriter:
    def write_turn(
        self,
        user_message: str,
        final_answer: str,
        llm_memory: dict | None,
    ) -> None:
        """
        Extract and persist memorable facts from a completed turn.
        """
        # Always extract user preferences from chat messages
        self._extract_user_preferences(user_message)

        if not llm_memory:
            return

        self._index_in_vector_store(user_message, final_answer, llm_memory)
        self._persist_to_project_memory(llm_memory)

    def _index_in_vector_store(
        self,
        user_message: str,
        final_answer: str,
        llm_memory: dict,
    ) -> None:
        """Add this turn to the persistent vector index."""
        try:
            from core.memory.vector_store import get_vector_store
            from core.session_manager import get_session_id

            store = get_vector_store()
            session_id = get_session_id()
            if not session_id:
                return

            entities_summary = llm_memory.get("entities_summary", "")
            files = ", ".join(llm_memory.get("files_touched", []))
            problems = " | ".join(llm_memory.get("problems_found", []))

            text = f"User: {user_message}\nResult: {entities_summary or final_answer[:300]}"
            if files:
                text += f"\nFiles: {files}"
            if problems:
                text += f"\nProblems: {problems}"

            import time

            key = f"turn:{session_id}:{int(time.time())}"
            store.upsert(key, text, metadata={"session": session_id})
        except Exception as e:
            logger.debug(f"MemoryWriter: vector index failed: {e}")

    def _persist_to_project_memory(self, llm_memory: dict) -> None:
        """Write memorable facts to ProjectMemory."""
        try:
            from core.memory.project_memory import get_project_memory

            pm = get_project_memory()

            for fact in llm_memory.get("solutions_applied", []):
                if any(kw in fact.lower() for kw in _TRIGGER_KEYWORDS):
                    pm.append("Key decisions", fact[:200], source="session")

            for decision in llm_memory.get("decisions", []):
                pm.append("Key decisions", decision[:200], source="session")

        except Exception as e:
            logger.debug(f"MemoryWriter: project memory persist failed: {e}")

    def _extract_user_preferences(self, user_message: str) -> None:
        """Extract and store user preferences from chat messages."""
        try:
            from core.memory.project_memory import get_project_memory

            pm = get_project_memory()
            msg_lower = user_message.lower()

            # Name patterns - check BEFORE general preference patterns
            name_patterns = [
                ("my name is ", "User's name is "),
                ("i am ", "User's name is "),
                ("i'm ", "User's name is "),
                ("call me ", "User goes by "),
            ]

            for pattern, prefix in name_patterns:
                if pattern in msg_lower:
                    idx = msg_lower.find(pattern)
                    rest = user_message[idx + len(pattern) :].strip()
                    # Get first word as name, avoid extracting verbs
                    if rest:
                        words = rest.split()
                        if words:
                            name = words[0].strip(".,!?")
                            # Only accept if it looks like a name (no verb tense)
                            if (
                                name
                                and len(name) > 1
                                and not any(
                                    v in name.lower()
                                    for v in [
                                        "am",
                                        "is",
                                        "are",
                                        "building",
                                        "working",
                                        "creating",
                                    ]
                                )
                            ):
                                pm.append(
                                    "User preferences", f"{prefix}{name}", source="chat"
                                )
                                break

            # Preference patterns
            pref_patterns = [
                ("prefer ", "User prefers "),
                ("i like ", "User likes "),
                ("i hate ", "User hates "),
                ("i love ", "User loves "),
                ("don't like ", "User doesn't like "),
                ("dont like ", "User doesn't like "),
            ]

            for pattern, prefix in pref_patterns:
                if pattern in msg_lower:
                    idx = msg_lower.find(pattern)
                    rest = user_message[idx + len(pattern) :].strip()
                    if rest:
                        # Get the object of preference
                        pref = rest.split(",")[0].split(".")[0].split(" and ")[0]
                        pref = pref.strip().strip(".,!?")
                        if pref and len(pref) > 1:
                            pm.append(
                                "User preferences", f"{prefix}{pref}", source="chat"
                            )

            # "I am building" pattern - only after name patterns
            building_patterns = [
                "i am building",
                "i'm building",
                "i am working on",
                "i'm working on",
            ]
            for pattern in building_patterns:
                if pattern in msg_lower:
                    idx = (
                        msg_lower.find("building")
                        if "building" in msg_lower
                        else msg_lower.find("working on")
                    )
                    if idx > 0:
                        rest = (
                            user_message[idx:]
                            .replace("building", "")
                            .replace("working on", "")
                            .strip()
                        )
                        if rest:
                            proj = rest.split(".")[0].split(",")[0].strip(".,!? ")
                            if proj and len(proj) > 2:
                                pm.append(
                                    "User preferences",
                                    f"User is building: {proj}",
                                    source="chat",
                                )
                                break

        except Exception as e:
            logger.debug(f"MemoryWriter: user preference extraction failed: {e}")


_writer: Optional[MemoryWriter] = None


def get_memory_writer() -> MemoryWriter:
    global _writer
    if _writer is None:
        _writer = MemoryWriter()
    return _writer
