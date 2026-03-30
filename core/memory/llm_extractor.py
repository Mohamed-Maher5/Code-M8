# core/memory/llm_extractor.py
# LLM-based entity extraction, compaction, and relationship tracking

from typing import List, Dict, Any, Optional
import json
from datetime import datetime


LLM_EXTRACTION_PROMPT = """You are a memory extraction system. Analyze this conversation turn and extract structured information.

Analyze the following:
- User message: what they asked for
- Agent results: what was done
- Final answer: what was accomplished

Extract EXACTLY this JSON structure (no markdown, no explanation):

{{
  "files_touched": ["filename.py", ...],
  "functions": ["function_name", ...],
  "classes": ["ClassName", ...],
  "concepts": ["api", "memory", "embedding", ...],
  "problems_found": ["bug description", ...],
  "solutions_applied": ["fix description", ...],
  "decisions": ["decision made", ...],
  "intent": "fix|implement|refactor|explore|delete|verify|general",
  "relationships": {{
    "builds_on": ["turn_id", ...],
    "related_to": ["turn_id", ...],
    "supersedes": ["turn_id", ...]
  }},
  "entities_summary": "2-3 sentence summary of what this turn accomplished"
}}

TURN DATA:
User Message: {user_message}

Agent Results:
{results}

Final Answer: {final_answer}

Return ONLY valid JSON:"""

COMPACTION_PROMPT = """You are a memory consolidation system. Combine multiple conversation turns into a concise summary.

Create a JSON object with:
{{
  "summary": "2-3 sentences capturing what was accomplished across all turns",
  "key_files": ["most important files", ...],
  "key_problems": ["major problems solved", ...],
  "key_solutions": ["major solutions applied", ...],
  "patterns": ["pattern1", "pattern2", ...],
  "turn_count": number of turns consolidated,
  "date": "YYYY-MM-DD"
}}

Recent turns to consolidate:
{turns}

Return ONLY valid JSON:"""

RELATIONSHIP_PROMPT = """You are a relationship analyzer. Given a new turn and previous turns, identify how they relate.

NEW TURN:
{new_turn}

PREVIOUS TURNS:
{previous_turns}

For each previous turn that relates to the new one, identify the relationship type:
- "builds_on": new turn continues work from previous
- "related_to": new turn is related but not directly building on
- "supersedes": new turn replaces/fixes previous turn's work
- "follows_up": new turn addresses something from previous

Return JSON:
{{
  "builds_on": ["turn_id1", ...],
  "related_to": ["turn_id2", ...],
  "supersedes": ["turn_id3", ...],
  "follows_up": ["turn_id4", ...]
}}

Return ONLY valid JSON:"""


def extract_with_llm(
    llm: Any,
    user_message: str,
    results: List[Dict],
    final_answer: str,
) -> Dict[str, Any]:
    """
    Use LLM to extract structured memory from a turn.

    Replaces regex-based extraction with intelligent LLM analysis.
    """
    # Format results for prompt
    results_text = ""
    for i, r in enumerate(results):
        task = r.get("task", {})
        agent = task.get("agent", "unknown")
        instruction = task.get("instruction", "")[:200]
        output = r.get("output", "")[:500]
        success = r.get("success", False)
        results_text += f"\n[Agent {i + 1}: {agent}] Instruction: {instruction}\nOutput: {output} (success={success})"

    prompt = LLM_EXTRACTION_PROMPT.format(
        user_message=user_message[:1000],
        results=results_text,
        final_answer=final_answer[:1000],
    )

    try:
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)

        # Parse JSON from response
        extracted = json.loads(content)

        return {
            "files_touched": extracted.get("files_touched", []),
            "functions": extracted.get("functions", []),
            "classes": extracted.get("classes", []),
            "concepts": extracted.get("concepts", []),
            "problems_found": extracted.get("problems_found", []),
            "solutions_applied": extracted.get("solutions_applied", []),
            "decisions": extracted.get("decisions", []),
            "intent": extracted.get("intent", "general"),
            "relationships": extracted.get(
                "relationships",
                {
                    "builds_on": [],
                    "related_to": [],
                    "supersedes": [],
                    "follows_up": [],
                },
            ),
            "entities_summary": extracted.get("entities_summary", ""),
        }
    except json.JSONDecodeError as e:
        print(f"[LLM EXTRACTOR] JSON parse error: {e}")
        return _fallback_extraction(user_message, results, final_answer)
    except Exception as e:
        print(f"[LLM EXTRACTOR] LLM call failed: {e}")
        return _fallback_extraction(user_message, results, final_answer)


def _fallback_extraction(
    user_message: str,
    results: List[Dict],
    final_answer: str,
) -> Dict[str, Any]:
    """Fallback if LLM extraction fails."""
    # Simple keyword-based fallback
    all_text = user_message + " " + final_answer

    files = []
    if "session" in all_text.lower():
        files.append("session_manager.py")
    if "memory" in all_text.lower():
        files.append("memory_index.py")
    if "graph" in all_text.lower() or "neo4j" in all_text.lower():
        files.append("graph_index.py")

    return {
        "files_touched": files,
        "functions": [],
        "classes": [],
        "concepts": [],
        "problems_found": [],
        "solutions_applied": [],
        "decisions": [],
        "intent": "general",
        "relationships": {
            "builds_on": [],
            "related_to": [],
            "supersedes": [],
            "follows_up": [],
        },
        "entities_summary": final_answer[:200] if final_answer else "",
    }


def compact_turns_with_llm(
    llm: Any,
    turns: List[Dict[str, Any]],
    max_turns: int = 10,
) -> Dict[str, Any]:
    """
    Use LLM to consolidate multiple older turns into a single summary.

    This is the "compaction" - older turns get condensed into rich summaries.
    """
    if not turns:
        return {
            "summary": "",
            "key_files": [],
            "key_problems": [],
            "key_solutions": [],
            "patterns": [],
            "turn_count": 0,
            "date": datetime.now().isoformat()[:10],
        }

    # Take the most recent max_turns
    turns_to_compact = turns[-max_turns:]

    # Format turns for prompt
    turns_text = ""
    for turn in turns_to_compact:
        turn_id = turn.get("turn_id", "???")
        user_msg = turn.get("user_message", "")[:300]
        final_ans = turn.get("final_answer", "")[:500]
        memory = turn.get("memory", {})
        entities = memory.get("entities", {})

        turns_text += f"""
---
Turn {turn_id}:
User: {user_msg}
Result: {final_ans}
Files: {entities.get("files", [])}
Problems: {memory.get("knowledge", {}).get("problems_found", [])}
Solutions: {memory.get("knowledge", {}).get("solutions_applied", [])}
---"""

    prompt = COMPACTION_PROMPT.format(turns=turns_text)

    try:
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)

        compacted = json.loads(content)

        return {
            "summary": compacted.get("summary", ""),
            "key_files": compacted.get("key_files", []),
            "key_problems": compacted.get("key_problems", []),
            "key_solutions": compacted.get("key_solutions", []),
            "patterns": compacted.get("patterns", []),
            "turn_count": len(turns_to_compact),
            "date": compacted.get("date", datetime.now().isoformat()[:10]),
        }
    except json.JSONDecodeError as e:
        print(f"[COMPACTION] JSON parse error: {e}")
        return _fallback_compaction(turns_to_compact)
    except Exception as e:
        print(f"[COMPACTION] LLM call failed: {e}")
        return _fallback_compaction(turns_to_compact)


def _fallback_compaction(turns: List[Dict]) -> Dict[str, Any]:
    """Fallback compaction using simple concatenation."""
    summaries = []
    files = set()
    problems = set()
    solutions = set()

    for turn in turns:
        memory = turn.get("memory", {})
        entities = memory.get("entities", {})

        files.update(entities.get("files", []))

        knowledge = memory.get("knowledge", {})
        problems.update(knowledge.get("problems_found", []))
        solutions.update(knowledge.get("solutions_applied", []))

        if turn.get("final_answer"):
            summaries.append(turn["final_answer"][:100])

    return {
        "summary": " | ".join(summaries[:3]),
        "key_files": list(files)[:5],
        "key_problems": list(problems)[:3],
        "key_solutions": list(solutions)[:3],
        "patterns": [],
        "turn_count": len(turns),
        "date": datetime.now().isoformat()[:10],
    }


def analyze_relationships_with_llm(
    llm: Any,
    new_turn: Dict[str, Any],
    previous_turns: List[Dict[str, Any]],
    max_previous: int = 5,
) -> Dict[str, List[str]]:
    """
    Use LLM to identify how a new turn relates to previous turns.

    This tracks: builds_on, related_to, supersedes, follows_up
    """
    if not previous_turns:
        return {
            "builds_on": [],
            "related_to": [],
            "supersedes": [],
            "follows_up": [],
        }

    # Format new turn
    new_turn_text = f"""
Turn {new_turn.get("turn_id", "???")}:
User: {new_turn.get("user_message", "")[:200]}
Result: {new_turn.get("final_answer", "")[:300]}
"""

    # Format previous turns (most recent first)
    prev_turns = previous_turns[-max_previous:]
    previous_text = ""
    for turn in prev_turns:
        turn_id = turn.get("turn_id", "???")
        user_msg = turn.get("user_message", "")[:150]
        final_ans = turn.get("final_answer", "")[:200]
        previous_text += f"\nTurn {turn_id}: User: {user_msg} | Result: {final_ans}"

    prompt = RELATIONSHIP_PROMPT.format(
        new_turn=new_turn_text,
        previous_turns=previous_text,
    )

    try:
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)

        relationships = json.loads(content)

        return {
            "builds_on": relationships.get("builds_on", []),
            "related_to": relationships.get("related_to", []),
            "supersedes": relationships.get("supersedes", []),
            "follows_up": relationships.get("follows_up", []),
        }
    except Exception as e:
        print(f"[RELATIONSHIPS] LLM call failed: {e}")
        return {
            "builds_on": [],
            "related_to": [],
            "supersedes": [],
            "follows_up": [],
        }


def create_compaction_schedule(total_turns: int) -> Dict[str, int]:
    """
    Determine when to compact turns.

    Example:
    - Turns 1-4: Keep as-is (recent)
    - Turns 5-20: Compact into 1 summary
    - Turns 21-100: Compact into 1 summary
    - Turns 100+: Compact into 1 summary

    Returns dict with compaction thresholds.
    """
    return {
        "recent_count": min(4, total_turns),  # Keep last 4 turns detailed
        "first_compaction_count": 5,  # Compact turns 5 onwards
        "second_compaction_threshold": 20,  # Compact turns 5-20 into 1
        "third_compaction_threshold": 100,  # Compact turns 21-100 into 1
    }
