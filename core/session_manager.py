# core/session_manager.py
# Saves and loads session history — one JSON file per session
# Stores full turn records on disk, returns only summaries to Orchestrator
#
# CHANGELOG (Option B - Better Context):
#   2026-03-29: Added _extract_mentioned_files() to track files per turn
#   2026-03-29: Enhanced save_turn() to store files_mentioned metadata
#   2026-03-29: Rewrote load_history() to return structured dicts (not flat strings)
#   2026-03-29: Added _format_turn() and _build_chat_context() helpers

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from core.config import SESSIONS_PATH
from core.token_usage import estimate_tokens
from utils.logger import logger

# current session id — set once when session starts, read everywhere
_current_session_id: str = ""
_DEFAULT_RECENT_TURNS = 4
_DEFAULT_MEMORY_BUDGET_CHARS = 6000


def create_session() -> str:
    """
    Creates a new session file and returns the session ID.
    Call this once when the terminal UI starts.
    """
    global _current_session_id

    # create sessions folder if it does not exist
    Path(SESSIONS_PATH).mkdir(parents=True, exist_ok=True)

    # generate unique session id
    _current_session_id = uuid.uuid4().hex[:8]

    # create empty session file
    session_file = _get_session_path(_current_session_id)
    session_file.write_text(json.dumps([]), encoding="utf-8")

    logger.info(f"Session created: {_current_session_id}")
    return _current_session_id


def reset_session() -> str:
    """
    Start a fresh session file and switch active session id.
    """
    return create_session()


def get_session_id() -> str:
    """Returns the current session ID."""
    return _current_session_id


# =============================================================================
# CHANGED: 2026-03-29 - Added _extract_mentioned_files() helper
# Purpose: Extract file paths from agent output for tracking
# =============================================================================
def _extract_mentioned_files(output: str) -> List[str]:
    """
    Extract file paths mentioned in agent output.

    Looks for common code file extensions to identify files.

    Args:
        output: The agent output text to search

    Returns:
        List of unique file paths/filenames found
    """
    # File extension patterns to match (non-capturing group to get full path)
    file_pattern = re.compile(
        r"[\w\-./\\]+\.(?:py|js|ts|jsx|tsx|html|css|json|yaml|yml|toml|xml|sql|sh|bash|go|rs|java|c|cpp|h|cs|swift|kt|php|rb|env|cfg|ini|md|txt|csv|pdf|png|jpg|lock|log)"
    )

    matches = file_pattern.findall(output)

    # Deduplicate while preserving order
    unique_files = list(dict.fromkeys(matches))

    # Filter out very short matches (likely false positives)
    unique_files = [f for f in unique_files if len(f) > 3]

    return unique_files


def _trim_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n...[trimmed]"


def _derive_intent(user_message: str) -> str:
    msg = user_message.lower()
    if any(w in msg for w in ("fix", "bug", "error", "broken")):
        return "fix"
    if any(w in msg for w in ("add", "create", "implement", "build", "make")):
        return "implement"
    if any(w in msg for w in ("refactor", "clean", "improve", "optimize")):
        return "refactor"
    if any(
        w in msg for w in ("explain", "how", "what", "why", "search", "find", "where")
    ):
        return "explore"
    if any(w in msg for w in ("delete", "remove", "undo")):
        return "delete"
    if any(w in msg for w in ("test", "verify", "check")):
        return "verify"
    return "general"


# Import enhanced entity extractors
try:
    from core.memory.entity_extractor import (
        extract_entities,
        extract_code_changes,
        detect_errors,
    )

    ENHANCED_EXTRACTION = True
except ImportError:
    ENHANCED_EXTRACTION = False

# LLM for extraction - set dynamically after loop.py initializes
_llm_for_extraction: Any = None
_llm_extraction_ready: bool = False


def set_llm_for_extraction(llm: Any) -> None:
    """Set the LLM instance for memory extraction. Called from loop.py."""
    global _llm_for_extraction, _llm_extraction_ready
    _llm_for_extraction = llm
    _llm_extraction_ready = llm is not None
    print(f"[SESSION MANAGER] LLM extraction enabled: {_llm_extraction_ready}")


def _derive_turn_memory(
    user_message: str,
    final_answer: str,
    all_results: list,
    files_mentioned: List[str],
) -> Dict[str, Any]:
    """
    Derive memory metadata from turn data.

    Uses LLM-based extraction when available, falls back to regex-based.
    """
    decisions: List[str] = []
    artifacts: List[str] = list(dict.fromkeys(files_mentioned))
    open_threads: List[str] = []

    # Try LLM-based extraction first
    if _llm_extraction_ready and _llm_for_extraction:
        try:
            from core.memory.llm_extractor import extract_with_llm

            llm_extracted = extract_with_llm(
                _llm_for_extraction,
                user_message,
                all_results,
                final_answer,
            )

            knowledge = {
                "problems_found": llm_extracted.get("problems_found", []),
                "solutions_applied": llm_extracted.get("solutions_applied", []),
                "learnings": [],
                "patterns_identified": [],
            }

            memory = {
                "intent": llm_extracted.get("intent", _derive_intent(user_message)),
                "decisions": llm_extracted.get("decisions", []),
                "open_threads": open_threads,
                "artifacts": artifacts,
                "entities": {
                    "files": llm_extracted.get("files_touched", []),
                    "functions": llm_extracted.get("functions", []),
                    "classes": llm_extracted.get("classes", []),
                    "concepts": llm_extracted.get("concepts", []),
                },
                "knowledge": knowledge,
                "relationships": llm_extracted.get(
                    "relationships",
                    {
                        "builds_on": [],
                        "related_to": [],
                        "follows_up": [],
                        "supersedes": [],
                    },
                ),
                "confidence": 0.9,
                "code_changes": [],
                "errors": [],
                "entities_summary": llm_extracted.get("entities_summary", ""),
                "extraction_method": "llm",
            }

            print(
                f"[MEMORY DEBUG] LLM extracted: {llm_extracted.get('files_touched', [])[:3]}..."
            )
            print(
                f"[MEMORY DEBUG] LLM knowledge: {len(knowledge.get('problems_found', []))} problems, {len(knowledge.get('solutions_applied', []))} solutions"
            )

            return memory

        except Exception as e:
            print(f"[MEMORY DEBUG] LLM extraction failed: {e}, falling back to regex")

    # Fall back to regex-based extraction
    if ENHANCED_EXTRACTION:
        try:
            # Extract entities (files, functions, classes, concepts)
            entities = extract_entities(user_message, all_results, final_answer)

            # Extract code changes
            code_changes = extract_code_changes(all_results)

            # Detect errors
            errors = detect_errors(all_results, final_answer)

            # Build knowledge section
            knowledge = {
                "problems_found": [],
                "solutions_applied": [],
                "learnings": [],
                "patterns_identified": [],
            }

            # Extract problems from errors
            for error in errors:
                if error.get("details"):
                    knowledge["problems_found"].append(error["details"][:100])

            # Extract solutions from code changes
            for change in code_changes:
                if change.get("success"):
                    knowledge["solutions_applied"].append(
                        f"{change['type']}: {change['file']}"
                    )

            # Build enhanced memory
            memory = {
                "intent": _derive_intent(user_message),
                "decisions": decisions,
                "open_threads": open_threads,
                "artifacts": artifacts,
                "entities": entities,
                "knowledge": knowledge,
                "relationships": {
                    "builds_on": [],
                    "related_to": [],
                    "follows_up": [],
                    "supersedes": [],
                },
                "confidence": 0.8,
                "code_changes": code_changes,
                "errors": errors,
                "extraction_method": "regex",
            }

            print(f"[MEMORY DEBUG] Regex extracted: {entities.get('files', [])[:3]}...")
            print(
                f"[MEMORY DEBUG] Regex knowledge: {len(knowledge.get('problems_found', []))} problems, {len(knowledge.get('solutions_applied', []))} solutions"
            )

            return memory

        except Exception as e:
            print(f"[MEMORY DEBUG] Enhanced extraction failed: {e}")

    # Ultimate fallback to original logic
    answer_l = final_answer.lower()
    if "next step" in answer_l or "you can now" in answer_l:
        decisions.append("assistant_provided_followup")
    if "not found" in answer_l or "could not" in answer_l or "failed" in answer_l:
        open_threads.append("unresolved_issue")

    for result in all_results:
        task = result.get("task", {})
        if task.get("agent") == "coder" and result.get("success"):
            decisions.append("code_changes_suggested")
        if not result.get("success", True):
            open_threads.append("agent_step_failed")

    return {
        "intent": _derive_intent(user_message),
        "decisions": list(dict.fromkeys(decisions)),
        "open_threads": list(dict.fromkeys(open_threads)),
        "artifacts": artifacts,
    }


# =============================================================================
# CHANGED: 2026-03-29 - Enhanced save_turn() with files_mentioned metadata
# Purpose: Track which files were mentioned in each turn for better context
# =============================================================================
def save_turn(
    user_message: str,
    all_results: list,
    final_answer: str,
) -> None:
    """
    Saves a completed turn to the session file.
    Call this at the end of every turn in loop.py.

    all_results is the list returned by dispatcher.run_plan()
    final_answer is the string returned by synthesizer.synthesize()

    CHANGED 2026-03-29: Now also extracts and stores files_mentioned.
    """
    if not _current_session_id:
        logger.warning("save_turn called but no active session — skipping")
        return

    # Extract files from all agent outputs for metadata tracking
    all_outputs = [r["output"] for r in all_results]
    all_outputs.append(final_answer)  # Include final answer too
    files_mentioned = _extract_mentioned_files(" ".join(all_outputs))

    memory = _derive_turn_memory(
        user_message=user_message,
        final_answer=final_answer,
        all_results=all_results,
        files_mentioned=files_mentioned,
    )

    # build the turn record - includes compact memory details
    turn_record = {
        "turn_id": _next_turn_id(),
        "timestamp": datetime.now().isoformat(),
        "user_message": user_message,
        "final_answer": final_answer,
        "files_mentioned": files_mentioned,  # NEW: 2026-03-29
        "memory": memory,
        "results": [
            {
                "agent": r["task"]["agent"],
                "instruction": r["task"]["instruction"],
                "output": r["output"],
                "success": r["success"],
            }
            for r in all_results
        ],
    }

    # load existing turns, append new one, save back
    session_file = _get_session_path(_current_session_id)

    try:
        existing = json.loads(session_file.read_text(encoding="utf-8"))
    except Exception:
        existing = []

    existing.append(turn_record)

    # Save initial turn record
    session_file.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # NEW: Analyze relationships with previous turns
    if _llm_extraction_ready and _llm_for_extraction and len(existing) > 1:
        try:
            from core.memory.llm_extractor import analyze_relationships_with_llm

            previous_turns = existing[:-1]  # All turns except current
            relationships = analyze_relationships_with_llm(
                _llm_for_extraction, turn_record, previous_turns
            )

            # Update the turn record with relationships
            existing[-1]["memory"]["relationships"] = relationships

            # Re-save with relationships
            session_file.write_text(
                json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            print(f"[RELATIONSHIPS] Analyzed: {relationships}")

        except Exception as e:
            print(f"[RELATIONSHIPS] Failed to analyze: {e}")

    logger.info(f"Turn {turn_record['turn_id']} saved to session {_current_session_id}")


# =============================================================================
# CHANGED: 2026-03-29 - Rewrote load_history() to return structured dicts
# Purpose: Provide richer context to orchestrator with file tracking
# =============================================================================
def load_history(last_n: int = 3, max_chars: int = 500) -> List[Dict[str, Any]]:
    """
    Returns the last N turns as structured dicts (not flat strings).

    This is what gets passed to orchestrator.plan() — provides richer context.

    CHANGED 2026-03-29:
      - Returns structured dicts instead of flat strings
      - Includes files_mentioned per turn
      - Uses max_chars parameter (default 500) instead of hardcoded 200

    Args:
        last_n: Number of recent turns to return (default: 3)
        max_chars: Max characters for final_answer in summary (default: 500)

    Returns:
        List of dicts with keys: turn_id, user_message, files_mentioned, summary
    """
    if not _current_session_id:
        return []

    session_file = _get_session_path(_current_session_id)

    if not session_file.exists():
        return []

    try:
        turns = json.loads(session_file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Failed to load session history: {e}")
        return []

    # take only the last N turns
    recent = turns[-last_n:]

    # Build structured history with richer context
    structured = []
    for t in recent:
        entry = {
            "turn_id": t.get("turn_id", "???"),
            "user_message": t.get("user_message", ""),
            "files_mentioned": t.get("files_mentioned", []),  # NEW: 2026-03-29
            "summary": t.get("final_answer", "")[
                :max_chars
            ],  # Increased from 200 to 500
            "memory": t.get("memory", {}),
        }
        structured.append(entry)

    return structured


# =============================================================================
# NEW: 2026-03-29 - Added _format_turn() helper
# Purpose: Format a single turn for orchestrator context
# =============================================================================
def _format_turn(turn: Dict[str, Any]) -> str:
    """
    Format a single structured turn into a readable string for orchestrator.

    Args:
        turn: Dict from load_history()

    Returns:
        Formatted string with turn info
    """
    files = turn.get("files_mentioned", [])
    files_str = f" (files: {', '.join(files)})" if files else ""

    return (
        f"Turn {turn['turn_id']} — "
        f"User: {turn['user_message']} — "
        f"Result: {turn['summary']}{files_str}"
    )


# =============================================================================
# NEW: 2026-03-29 - Added _build_chat_context() helper
# Purpose: Build richer context for chat replies with file awareness
# =============================================================================
def _build_chat_context(history: List[Dict[str, Any]]) -> str:
    """
    Build a rich context string for chat replies.

    Includes both conversation flow and file awareness.

    Args:
        history: List from load_history()

    Returns:
        Rich context string for chat replies
    """
    if not history:
        return ""

    # Build conversation summary
    conv_lines = ["Recent conversation:"]

    for turn in history:
        files = turn.get("files_mentioned", [])
        files_str = f" (touched: {', '.join(files)})" if files else ""

        conv_lines.append(f"  User: {turn['user_message']}{files_str}")
        conv_lines.append(f"  Assistant: {turn['summary'][:200]}...")

    return "\n".join(conv_lines)


def build_compact_memory(
    recent_turns: int = _DEFAULT_RECENT_TURNS,
    max_total_chars: int = _DEFAULT_MEMORY_BUDGET_CHARS,
    per_turn_chars: int = 700,
) -> Dict[str, Any]:
    """
    Build a compact memory package for planning:
      - rolling_summary: compressed older context
      - recent_turns: detailed recent turns
      - files_mentioned: deduplicated recent files
    """
    # DEBUG: Start of build_compact_memory
    print("\n" + "=" * 80)
    print("[MEMORY DEBUG] ══ build_compact_memory() START ══")
    print(
        f"  Parameters: recent_turns={recent_turns}, max_total_chars={max_total_chars}, per_turn_chars={per_turn_chars}"
    )
    print("=" * 80)

    if not _current_session_id:
        print("[MEMORY DEBUG] No session_id, returning empty compact_memory")
        return {"rolling_summary": "", "recent_turns": [], "files_mentioned": []}

    session_file = _get_session_path(_current_session_id)
    print(f"[MEMORY DEBUG] Session file: {session_file}")

    if not session_file.exists():
        print(
            "[MEMORY DEBUG] Session file does not exist, returning empty compact_memory"
        )
        return {"rolling_summary": "", "recent_turns": [], "files_mentioned": []}

    try:
        turns = json.loads(session_file.read_text(encoding="utf-8"))
        print(f"[MEMORY DEBUG] Loaded {len(turns)} turns from session file")
    except Exception as e:
        logger.error(f"Failed to load compact memory: {e}")
        print(f"[MEMORY DEBUG] ERROR loading session: {e}")
        return {"rolling_summary": "", "recent_turns": [], "files_mentioned": []}

    if not turns:
        print("[MEMORY DEBUG] No turns in session, returning empty compact_memory")
        return {"rolling_summary": "", "recent_turns": [], "files_mentioned": []}

    print(f"[MEMORY DEBUG] Splitting turns:")
    print(f"  - Total turns: {len(turns)}")

    recent_raw = turns[-recent_turns:]
    older_raw = turns[:-recent_turns]
    print(
        f"  - recent_raw (last {len(recent_raw)} turns): {[t.get('turn_id', '???') for t in recent_raw]}"
    )
    print(
        f"  - older_raw (first {len(older_raw)} turns): oldest={older_raw[0].get('turn_id', '???') if older_raw else 'N/A'}, newest={older_raw[-1].get('turn_id', '???') if older_raw else 'N/A'}"
    )

    print("\n[MEMORY DEBUG] Processing RECENT turns (detailed):")
    recent_structured: List[Dict[str, Any]] = []
    all_files: List[str] = []
    for i, turn in enumerate(recent_raw):
        files = turn.get("files_mentioned", [])
        all_files.extend(files)
        user_msg = turn.get("user_message", "")
        final_ans = turn.get("final_answer", "")
        turn_summary = _trim_text(final_ans, per_turn_chars)

        print(f"  Turn {i + 1} (id={turn.get('turn_id', '???')}):")
        print(f"    - user_message: '{user_msg[:60]}...' ({len(user_msg)} chars)")
        print(
            f"    - final_answer: '{final_ans[:60]}...' ({len(final_ans)} chars) -> trimmed to {len(turn_summary)} chars"
        )
        print(f"    - files: {files}")

        recent_structured.append(
            {
                "turn_id": turn.get("turn_id", "???"),
                "user_message": _trim_text(user_msg, 220),
                "summary": turn_summary,
                "files_mentioned": files,
                "memory": turn.get("memory", {}),
            }
        )
    print(f"[MEMORY DEBUG] Recent turns processed: {len(recent_structured)} turns")
    print(f"[MEMORY DEBUG] All files collected: {all_files}")

    print("\n[MEMORY DEBUG] Processing OLDER turns (rolling summary):")
    print(f"  - Processing last 20 turns from {len(older_raw)} older turns")
    rolling_lines: List[str] = []
    for i, turn in enumerate(older_raw[-20:]):  # Max 20 turns in rolling
        mem = turn.get("memory", {})
        intent = mem.get("intent", "general")
        decisions = ", ".join(mem.get("decisions", [])[:2])
        open_threads = ", ".join(mem.get("open_threads", [])[:2])
        user = _trim_text(turn.get("user_message", ""), 120)
        result = _trim_text(turn.get("final_answer", ""), 200)
        line = f"- T{turn.get('turn_id', '???')} [{intent}] {user} -> {result}"
        if decisions:
            line += f" | decisions: {decisions}"
        if open_threads:
            line += f" | open: {open_threads}"
        rolling_lines.append(line)
        print(
            f"  [{i + 1}] T{turn.get('turn_id', '???')} [{intent}]: '{user[:40]}...' -> '{result[:40]}...'"
        )

    rolling_summary = "\n".join(rolling_lines)
    rolling_summary = _trim_text(rolling_summary, max_total_chars)

    print(f"\n[MEMORY DEBUG] Rolling summary stats:")
    print(f"  - Total lines: {len(rolling_lines)}")
    print(f"  - Raw length: {len(rolling_summary)} chars")
    print(
        f"  - After trim (max_total_chars={max_total_chars}): {len(rolling_summary)} chars"
    )
    print(f"  - Est tokens: {estimate_tokens(rolling_summary)}")

    deduplicated_files = list(dict.fromkeys(all_files))
    print(f"\n[MEMORY DEBUG] Files mentioned:")
    print(f"  - Before dedup: {len(all_files)}")
    print(f"  - After dedup: {len(deduplicated_files)}")
    print(f"  - Files: {deduplicated_files}")

    result = {
        "rolling_summary": rolling_summary,
        "recent_turns": recent_structured,
        "files_mentioned": deduplicated_files,
    }

    print(f"\n[MEMORY DEBUG] ══ build_compact_memory() COMPLETE ══")
    print(f"  - rolling_summary length: {len(result['rolling_summary'])} chars")
    print(f"  - recent_turns count: {len(result['recent_turns'])}")
    print(f"  - files_mentioned count: {len(result['files_mentioned'])}")
    print("=" * 80 + "\n")

    return result


def build_llm_compacted_memory() -> Dict[str, Any]:
    """
    Build memory using LLM-based compaction.

    This provides richer, more contextual memory summaries
    compared to the basic rolling summary.
    """
    if not _current_session_id:
        return {"summary": "", "recent": [], "compacted": []}

    if not _llm_extraction_ready or not _llm_for_extraction:
        return build_compact_memory()

    try:
        from core.memory.compaction import get_compaction_manager

        manager = get_compaction_manager()
        memory_str = manager.get_memory_for_planning(
            _llm_for_extraction, _current_session_id
        )

        return {
            "llm_compacted": memory_str,
            "method": "llm",
        }
    except Exception as e:
        print(f"[LLM COMPACTION] Failed: {e}")
        return build_compact_memory()


# ── Private helpers ───────────────────────────────────────────────────────────


def _get_session_path(session_id: str) -> Path:
    return Path(SESSIONS_PATH) / f"{session_id}.json"


def _next_turn_id() -> str:
    """Reads current turn count from session file and returns next ID."""
    if not _current_session_id:
        return "001"

    session_file = _get_session_path(_current_session_id)

    try:
        turns = json.loads(session_file.read_text(encoding="utf-8"))
        return str(len(turns) + 1).zfill(3)
    except Exception:
        return "001"
