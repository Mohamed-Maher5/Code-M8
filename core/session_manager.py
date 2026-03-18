# core/session_manager.py
# Saves and loads session history — one JSON file per session
# Stores full turn records on disk, returns only summaries to Orchestrator

import json
import uuid
from datetime import datetime
from pathlib import Path

from core.config import SESSIONS_PATH
from utils.logger import logger

# current session id — set once when session starts, read everywhere
_current_session_id: str = ""


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


def get_session_id() -> str:
    """Returns the current session ID."""
    return _current_session_id


def save_turn(
    user_message: str,
    all_results : list,
    final_answer: str,
) -> None:
    """
    Saves a completed turn to the session file.
    Call this at the end of every turn in loop.py.

    all_results is the list returned by dispatcher.run_plan()
    final_answer is the string returned by synthesizer.synthesize()
    """
    if not _current_session_id:
        logger.warning("save_turn called but no active session — skipping")
        return

    # build the turn record
    turn_record = {
        "turn_id"     : _next_turn_id(),
        "timestamp"   : datetime.now().isoformat(),
        "user_message": user_message,
        "final_answer": final_answer,
        "results"     : [
            {
                "agent"      : r["task"]["agent"],
                "instruction": r["task"]["instruction"],
                "output"     : r["output"],
                "success"    : r["success"],
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

    session_file.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    logger.info(f"Turn {turn_record['turn_id']} saved to session {_current_session_id}")


def load_history(last_n: int = 5) -> list[str]:
    """
    Returns the last N turns as short summary strings.
    This is what gets passed to orchestrator.plan() — NOT the full records.
    Each string is roughly 50 tokens — safe to pass as session context.
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

    # return only user_message + final_answer — nothing else
    summaries = []
    for t in recent:
        summary = (
            f"Turn {t['turn_id']} — "
            f"User: {t['user_message']} — "
            f"Result: {t['final_answer'][:200]}"  # cap at 200 chars
        )
        summaries.append(summary)

    return summaries


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