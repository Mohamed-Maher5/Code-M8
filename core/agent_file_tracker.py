# core/agent_file_tracker.py
# Tracks all files created/modified during agent execution

import os
import json
from pathlib import Path
from typing import List, Dict, Set
from datetime import datetime
from threading import Lock

from core.config import WORKSPACE_PATH

_tracker_lock = Lock()
_created_files: Set[str] = set()
_modified_files: Set[str] = set()

# Track original file mtimes for detecting modifications
_original_mtimes: Dict[str, float] = {}


def reset_tracker() -> None:
    """Reset the tracker for a new turn"""
    global _created_files, _modified_files, _original_mtimes
    with _tracker_lock:
        _created_files = set()
        _modified_files = set()
        _original_mtimes = {}


def record_file_created(file_path: str) -> None:
    """Record a newly created file"""
    with _tracker_lock:
        _created_files.add(file_path)


def record_file_modified(file_path: str) -> None:
    """Record a modified file"""
    with _tracker_lock:
        _modified_files.add(file_path)


def check_file_status(file_path: str) -> str:
    """Check if a file is new or modified"""
    workspace = Path(WORKSPACE_PATH).resolve()
    full_path = (workspace / file_path).resolve()

    if not full_path.exists():
        return "unknown"

    with _tracker_lock:
        if file_path in _created_files:
            return "created"
        if file_path in _modified_files:
            return "modified"

        # Check if file exists but wasn't tracked - it's existing
        return "existing"


def init_file_tracking() -> None:
    """Initialize tracking by recording current file state"""
    workspace = Path(WORKSPACE_PATH).resolve()
    if not workspace.exists():
        return

    global _original_mtimes
    with _tracker_lock:
        for root, dirs, files in os.walk(workspace):
            dirs[:] = [
                d
                for d in dirs
                if d not in {".git", "__pycache__", "node_modules", ".venv"}
            ]
            for f in files:
                full_path = os.path.join(root, f)
                try:
                    _original_mtimes[full_path] = os.path.getmtime(full_path)
                except:
                    pass


def get_tracked_files() -> Dict[str, List[str]]:
    """Get all tracked files"""
    with _tracker_lock:
        return {
            "created": sorted(list(_created_files)),
            "modified": sorted(list(_modified_files)),
            "all": sorted(list(_created_files | _modified_files)),
        }


def scan_workspace_for_changes() -> Dict[str, List[str]]:
    """Scan workspace for any new or modified files since last check"""
    workspace = Path(WORKSPACE_PATH).resolve()
    created = []
    modified = []

    if not workspace.exists():
        return {"created": created, "modified": modified}

    global _original_mtimes

    for root, dirs, files in os.walk(workspace):
        dirs[:] = [
            d for d in dirs if d not in {".git", "__pycache__", "node_modules", ".venv"}
        ]

        for f in files:
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, workspace)

            try:
                current_mtime = os.path.getmtime(full_path)

                if full_path not in _original_mtimes:
                    created.append(rel_path)
                elif _original_mtimes[full_path] < current_mtime:
                    modified.append(rel_path)

                _original_mtimes[full_path] = current_mtime
            except:
                pass

    with _tracker_lock:
        _created_files.update(created)
        _modified_files.update(modified)

    return {"created": created, "modified": modified}


def get_session_file_summary() -> str:
    """Get a human-readable summary of tracked files"""
    tracked = get_tracked_files()

    if not tracked["all"]:
        return "No files created or modified in this session."

    parts = []
    if tracked["created"]:
        parts.append(f"Created: {', '.join(tracked['created'][:5])}")
        if len(tracked["created"]) > 5:
            parts.append(f"  ... and {len(tracked['created']) - 5} more")
    if tracked["modified"]:
        parts.append(f"Modified: {', '.join(tracked['modified'][:5])}")
        if len(tracked["modified"]) > 5:
            parts.append(f"  ... and {len(tracked['modified']) - 5} more")

    return " | ".join(parts)
