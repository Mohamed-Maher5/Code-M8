# core/memory/retrieval.py
# Memory retrieval and context building for orchestrator

from typing import Dict, Any, List, Optional
from core.memory.memory_index import get_memory_index, load_session_into_index
from core.session_manager import get_session_id


def retrieve_relevant_memory(query: str, session_id: str = None) -> Dict[str, Any]:
    """
    Retrieve relevant memory for a query.

    This is the main entry point for getting memory context.

    Returns:
        {
            "related_turns": [...],
            "relevant_files": [...],
            "problems_to_avoid": [...],
            "solutions_to_reuse": [...],
            "context": {...}
        }
    """
    # Use current session if not specified
    if session_id is None:
        session_id = get_session_id()

    if not session_id:
        print("[MEMORY RETRIEVAL] No session ID available")
        return _empty_memory_context()

    # Load session into memory index if needed
    load_session_into_index(session_id)

    index = get_memory_index()

    # Semantic search
    results = index.search(query, k=3)

    if not results:
        print(f"[MEMORY RETRIEVAL] No relevant memory found for: {query[:50]}...")
        return _empty_memory_context()

    # Extract relevant information
    related_turns = []
    relevant_files = set()
    problems_to_avoid = set()
    solutions_to_reuse = set()

    for turn in results:
        related_turns.append(turn.get("turn_id", "???"))

        # Extract files
        memory = turn.get("memory", {})
        artifacts = memory.get("artifacts", [])
        relevant_files.update(artifacts)

        # Extract entities
        entities = memory.get("entities", {})
        relevant_files.update(entities.get("files", []))

        # Extract problems and solutions
        knowledge = turn.get("knowledge", {})
        problems_to_avoid.update(knowledge.get("problems_found", []))
        solutions_to_reuse.update(knowledge.get("solutions_applied", []))

    context = {
        "query": query,
        "top_result": results[0] if results else None,
        "all_results": results,
    }

    result = {
        "related_turns": related_turns,
        "relevant_files": sorted(list(relevant_files))[:10],
        "problems_to_avoid": sorted(list(problems_to_avoid))[:5],
        "solutions_to_reuse": sorted(list(solutions_to_reuse))[:5],
        "context": context,
    }

    print(
        f"[MEMORY RETRIEVAL] Found {len(related_turns)} related turns, {len(relevant_files)} files"
    )

    return result


def _empty_memory_context() -> Dict[str, Any]:
    """Return empty memory context structure."""
    return {
        "related_turns": [],
        "relevant_files": [],
        "problems_to_avoid": [],
        "solutions_to_reuse": [],
        "context": {},
    }


def build_memory_context_for_orchestrator(
    user_request: str, session_id: str = None
) -> str:
    """
    Build a context string for the orchestrator with relevant memory.

    This formats memory into a string that can be added to orchestrator context.
    """
    memory = retrieve_relevant_memory(user_request, session_id=session_id)

    if not memory.get("related_turns"):
        return ""

    lines = ["--- RELEVANT MEMORY ---"]

    # Related turns
    if memory["related_turns"]:
        lines.append(f"Related previous turns: {', '.join(memory['related_turns'])}")

    # Files to check
    if memory["relevant_files"]:
        lines.append(f"Files to check: {', '.join(memory['relevant_files'][:5])}")

    # Problems to avoid
    if memory["problems_to_avoid"]:
        lines.append(f"Known problems: {', '.join(memory['problems_to_avoid'])}")

    # Solutions to reuse
    if memory["solutions_to_reuse"]:
        lines.append(f"Previous solutions: {', '.join(memory['solutions_to_reuse'])}")

    # Add context from top result
    if memory.get("context", {}).get("top_result"):
        top = memory["context"]["top_result"]
        user_msg = top.get("user_message", "")
        if user_msg:
            lines.append(f"Similar past request: {user_msg[:100]}")

    lines.append("--- END MEMORY ---")

    return "\n".join(lines)


def get_session_memory_summary(session_id: str = None) -> Dict[str, Any]:
    """Get a summary of the current session memory."""
    if session_id is None:
        session_id = get_session_id()

    if not session_id:
        return {"error": "No session available"}

    load_session_into_index(session_id)
    index = get_memory_index()

    return {
        "total_turns": len(index.turns),
        "files_worked_on": index.get_files_worked_on(),
        "problems_and_solutions": index.get_problems_and_solutions(),
    }
