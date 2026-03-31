# core/memory/memory_index.py
# Semantic memory search over conversation history

import numpy as np
from typing import List, Dict, Any, Optional
from pathlib import Path
import json

# We'll use the existing embedding function
try:
    from context.graph_config import embed

    EMBED_AVAILABLE = True
except ImportError:
    EMBED_AVAILABLE = False
    print(
        "[MEMORY INDEX] Warning: Embeddings not available, using keyword search fallback"
    )


class MemoryIndex:
    """
    Semantic search over conversation history.

    Uses embeddings to find relevant previous turns based on
    semantic similarity to current query.
    """

    def __init__(self):
        self.turns: List[Dict] = []
        self.embeddings: List[np.ndarray] = []
        self._index_loaded = False

    def load_from_session(
        self, session_id: str, sessions_path: str = "sessions"
    ) -> None:
        """Load turns from a session file into the index."""
        session_file = Path(sessions_path) / f"{session_id}.json"

        if not session_file.exists():
            print(f"[MEMORY INDEX] Session file not found: {session_file}")
            return

        try:
            turns = json.loads(session_file.read_text(encoding="utf-8"))
            print(f"[MEMORY INDEX] Loaded {len(turns)} turns from session {session_id}")

            for turn in turns:
                self.add_turn(turn)

            self._index_loaded = True
            print(f"[MEMORY INDEX] Indexed {len(self.turns)} turns")

        except Exception as e:
            print(f"[MEMORY INDEX] Error loading session: {e}")

    def add_turn(self, turn: Dict[str, Any]) -> None:
        """Add a turn to the memory index."""
        self.turns.append(turn)

        # Generate embedding for this turn
        if EMBED_AVAILABLE:
            summary = self._create_summary(turn)
            try:
                embedding = embed(summary)
                # Ensure 2D array
                if embedding.ndim == 1:
                    embedding = embedding.reshape(1, -1)
                self.embeddings.append(embedding[0])  # Store 1D array
            except Exception as e:
                print(f"[MEMORY INDEX] Error generating embedding: {e}")
                self.embeddings.append(np.zeros(384))
        else:
            # Placeholder if embeddings not available
            self.embeddings.append(np.zeros(384))

    def _create_summary(self, turn: Dict[str, Any]) -> str:
        """Create a semantic summary of a turn for embedding."""
        parts = []

        # User request
        user_msg = turn.get("user_message", "")
        if user_msg:
            parts.append(f"User asked: {user_msg}")

        # Entities (files, functions, etc.)
        memory = turn.get("memory", {})
        entities = memory.get("entities", {})

        if entities.get("files"):
            parts.append(f"Files involved: {', '.join(entities['files'])}")

        if entities.get("concepts"):
            parts.append(f"Concepts: {', '.join(entities['concepts'])}")

        # Knowledge (problems, solutions)
        knowledge = turn.get("knowledge", {})

        if knowledge.get("problems_found"):
            parts.append(f"Problems: {', '.join(knowledge['problems_found'])}")

        if knowledge.get("solutions_applied"):
            parts.append(f"Solutions: {', '.join(knowledge['solutions_applied'])}")

        # Decisions
        if memory.get("decisions"):
            parts.append(f"Decisions: {', '.join(memory['decisions'])}")

        return " | ".join(parts) if parts else user_msg

    def search(self, query: str, k: int = 3) -> List[Dict[str, Any]]:
        """
        Find most relevant previous turns to the query.

        Args:
            query: The search query
            k: Number of results to return

        Returns:
            List of relevant turns with similarity scores
        """
        if not self.turns:
            print("[MEMORY INDEX] No turns in index")
            return []

        if not EMBED_AVAILABLE:
            # Fallback to keyword search
            return self._keyword_search(query, k)

        try:
            # Generate query embedding
            query_emb = embed(query)
            if query_emb.ndim == 1:
                query_emb = query_emb.reshape(1, -1)
            query_emb = query_emb[0]

            # Calculate similarities
            scores = []
            for i, emb in enumerate(self.embeddings):
                if emb is None or len(emb) == 0:
                    continue

                # Cosine similarity
                sim = np.dot(query_emb, emb) / (
                    np.linalg.norm(query_emb) * np.linalg.norm(emb) + 1e-8
                )
                scores.append((i, sim))

            # Sort by score descending
            scores.sort(key=lambda x: x[1], reverse=True)

            # Return top k with scores
            results = []
            for i, score in scores[:k]:
                turn = self.turns[i].copy()
                turn["_similarity_score"] = float(score)
                results.append(turn)

            print(
                f"[MEMORY INDEX] Search '{query[:30]}...' found {len(results)} results"
            )
            return results

        except Exception as e:
            print(f"[MEMORY INDEX] Search error: {e}")
            return self._keyword_search(query, k)

    def _keyword_search(self, query: str, k: int) -> List[Dict]:
        """Fallback keyword-based search."""
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scores = []
        for i, turn in enumerate(self.turns):
            score = 0

            # Check user message
            user_msg = turn.get("user_message", "").lower()
            if any(word in user_msg for word in query_words):
                score += 2

            # Check files mentioned
            memory = turn.get("memory", {})
            files = memory.get("artifacts", [])
            for f in files:
                if any(word in f.lower() for word in query_words):
                    score += 1

            # Check knowledge - Bug 6 Fix: correct path
            knowledge = turn.get("memory", {}).get(
                "knowledge", {}
            )  # was: turn.get("knowledge", {})
            for problem in knowledge.get("problems_found", []):
                if any(word in problem.lower() for word in query_words):
                    score += 1

            scores.append((i, score))

        scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for i, score in scores[:k]:
            if score > 0:
                turn = self.turns[i].copy()
                turn["_similarity_score"] = score
                results.append(turn)

        return results

    def get_related_turns(self, turn_id: str, k: int = 3) -> List[Dict]:
        """Find turns related to a specific turn."""
        # Find the turn index
        idx = None
        for i, t in enumerate(self.turns):
            if t.get("turn_id") == turn_id:
                idx = i
                break

        if idx is None:
            return []

        # Use relationships if available
        turn = self.turns[idx]
        relationships = turn.get("relationships", {})

        related = []
        for rel_type in ["related_to", "builds_on", "follows_up"]:
            for related_id in relationships.get(rel_type, []):
                for t in self.turns:
                    if t.get("turn_id") == related_id:
                        related.append(t)

        return related[:k]

    def get_files_worked_on(self) -> List[str]:
        """Get list of all files mentioned across all turns."""
        files = set()

        for turn in self.turns:
            memory = turn.get("memory", {})
            artifacts = memory.get("artifacts", [])
            files.update(artifacts)

        return sorted(list(files))

    def get_problems_and_solutions(self) -> Dict[str, List[str]]:
        """Get all problems and solutions across turns."""
        problems = set()
        solutions = set()

        for turn in self.turns:
            # Bug 6 Fix: correct path
            knowledge = turn.get("memory", {}).get(
                "knowledge", {}
            )  # was: turn.get("knowledge", {})
            problems.update(knowledge.get("problems_found", []))
            solutions.update(knowledge.get("solutions_applied", []))

        return {
            "problems": sorted(list(problems)),
            "solutions": sorted(list(solutions)),
        }

    def clear(self) -> None:
        """Clear the memory index."""
        self.turns.clear()
        self.embeddings.clear()
        self._index_loaded = False
        print("[MEMORY INDEX] Index cleared")


# Global memory index instance
_memory_index: Optional[MemoryIndex] = None


def get_memory_index() -> MemoryIndex:
    """Get or create the global memory index."""
    global _memory_index
    if _memory_index is None:
        _memory_index = MemoryIndex()
    return _memory_index


def load_session_into_index(session_id: str) -> None:
    """Load a session into the global memory index."""
    index = get_memory_index()
    index.clear()
    index.load_from_session(session_id)
