# core/spec_store.py
# Holds parsed acceptance criteria for the current session.
# Criteria are written once (when the user provides a spec) and read
# by Orchestrator.plan(), digest(), and Synthesizer.synthesize().
#
# Storage: <sessions_path>/<session_id>_spec.json
# Format : list of criterion dicts  (same schema as read_spec output)
#
# Thread-safety: single-process only — no locking needed.

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from core.config import SESSIONS_PATH
from utils.logger import logger


# ── Criterion type alias ───────────────────────────────────────────────────────
# {id, description, category, priority, testable}
Criterion = dict


# ── Module-level state ────────────────────────────────────────────────────────
_criteria    : List[Criterion] = []
_session_id  : str             = ""
_spec_source : str             = ""   # human-readable label ("specs/login.md" or "inline")


# ── Public API ────────────────────────────────────────────────────────────────

def init(session_id: str) -> None:
    """Call once when session starts (after create_session())."""
    global _session_id
    _session_id = session_id
    _load_from_disk()


def set_criteria(criteria: List[Criterion], source: str = "inline") -> None:
    """Store a parsed criteria list and persist to disk."""
    global _criteria, _spec_source
    _criteria    = criteria
    _spec_source = source
    _save_to_disk()
    logger.info(f"SpecStore: {len(_criteria)} criteria saved from '{_spec_source}'")


def get_criteria() -> List[Criterion]:
    """Return the current criteria list (empty list if none loaded)."""
    return list(_criteria)


def has_spec() -> bool:
    return bool(_criteria)


def clear() -> None:
    """Remove criteria from memory and disk."""
    global _criteria, _spec_source
    _criteria    = []
    _spec_source = ""
    _delete_from_disk()
    logger.info("SpecStore: cleared")


def summary_text() -> str:
    """One-line human summary — used in UI status display."""
    if not _criteria:
        return "no spec loaded"
    musts    = sum(1 for c in _criteria if c.get("priority") == "must")
    shoulds  = sum(1 for c in _criteria if c.get("priority") == "should")
    testable = sum(1 for c in _criteria if c.get("testable"))
    return (
        f"{len(_criteria)} criteria from '{_spec_source}' "
        f"({musts} must, {shoulds} should, {testable} testable)"
    )


def as_injection_text() -> str:
    """Formatted block injected into Orchestrator digest() and Coder instruction.

    Example output:
        ACCEPTANCE CRITERIA (from specs/login.md):
        [AC-001] (must/functional) The /login endpoint accepts POST requests.
        [AC-002] (must/security)   Passwords must be hashed with bcrypt.
        [AC-003] (should/ux)       Login errors return a human-readable message.
    """
    if not _criteria:
        return ""

    lines = [f"ACCEPTANCE CRITERIA (from {_spec_source}):"]
    for c in _criteria:
        testable_tag = " [testable]" if c.get("testable") else ""
        lines.append(
            f"  [{c['id']}] ({c['priority']}/{c['category']}){testable_tag} "
            f"{c['description']}"
        )
    return "\n".join(lines)


def as_checklist_text() -> str:
    """Used by Synthesizer — same list but with placeholder status markers.

    The Synthesizer LLM fills in PASS / PARTIAL / FAIL for each item.
    """
    if not _criteria:
        return ""

    lines = [f"CRITERIA CHECKLIST (from {_spec_source}):"]
    for c in _criteria:
        lines.append(
            f"  [{c['id']}] {c['description']} → STATUS: ???"
        )
    return "\n".join(lines)


# ── Disk persistence ──────────────────────────────────────────────────────────

def _spec_path() -> Optional[Path]:
    if not _session_id:
        return None
    Path(SESSIONS_PATH).mkdir(parents=True, exist_ok=True)
    return Path(SESSIONS_PATH) / f"{_session_id}_spec.json"


def _save_to_disk() -> None:
    path = _spec_path()
    if path is None:
        return
    try:
        payload = {"source": _spec_source, "criteria": _criteria}
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.error(f"SpecStore: failed to save to disk: {e}")


def _load_from_disk() -> None:
    global _criteria, _spec_source
    path = _spec_path()
    if path is None or not path.exists():
        return
    try:
        payload      = json.loads(path.read_text(encoding="utf-8"))
        _criteria    = payload.get("criteria", [])
        _spec_source = payload.get("source", "unknown")
        logger.info(f"SpecStore: loaded {len(_criteria)} criteria from disk")
    except Exception as e:
        logger.error(f"SpecStore: failed to load from disk: {e}")


def _delete_from_disk() -> None:
    path = _spec_path()
    if path and path.exists():
        try:
            path.unlink()
        except Exception as e:
            logger.error(f"SpecStore: failed to delete spec file: {e}")