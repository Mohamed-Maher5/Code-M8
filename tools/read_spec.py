# tools/read_spec.py
# Parses a spec / PRD / issue into structured acceptance criteria.
# Accepts either a file path (inside workspace) OR inline text.
# Returns a JSON string — list of criterion dicts — ready for SpecStore.
#
# Schema per criterion:
#   {
#     "id":          "AC-001",          # sequential, stable across turns
#     "description": "...",             # one plain-English sentence
#     "category":    "functional|perf|security|ux|other",
#     "priority":    "must|should|nice",
#     "testable":    true|false         # can a unit test verify this?
#   }

from __future__ import annotations

import json
import os
from pathlib import Path

from langchain_core.tools import tool

import core.config as CONFIG


# ── LLM prompt ────────────────────────────────────────────────────────────────

_PARSE_SYSTEM = """You are a requirements analyst.
Extract every acceptance criterion from the text below.
Return ONLY a valid JSON array — no markdown, no explanation, no preamble.

Each element must have exactly these keys:
  "id"          : string  — "AC-001", "AC-002", … (sequential, zero-padded)
  "description" : string  — one clear, testable sentence in plain English
  "category"    : string  — one of: functional | perf | security | ux | other
  "priority"    : string  — one of: must | should | nice
  "testable"    : boolean — true if a unit/integration test can verify this

Rules:
- Extract EVERY requirement, including implicit ones (e.g. "the endpoint must exist")
- Each criterion must be atomic (one thing only)
- Do NOT merge multiple requirements into one item
- Do NOT add criteria that are not in the text
- Output nothing except the JSON array"""


# ── Tool ──────────────────────────────────────────────────────────────────────

@tool
def read_spec(source: str) -> str:
    """Parse a spec document or inline text into structured acceptance criteria.

    Accepts either:
      - A file path relative to the workspace root  (e.g. "specs/login.md")
      - Inline spec text  (anything longer than a file path or not ending in a
        known extension is treated as inline text)

    Returns a JSON string: list of acceptance criteria dicts with keys:
      id, description, category, priority, testable

    Example output:
      [
        {"id": "AC-001", "description": "The /login endpoint accepts POST requests",
         "category": "functional", "priority": "must", "testable": true},
        ...
      ]
    """
    if not source or not source.strip():
        return json.dumps({"error": "source is empty"})

    raw_text = _resolve_source(source.strip())
    if raw_text.startswith("ERROR:"):
        return json.dumps({"error": raw_text})

    criteria = _parse_with_llm(raw_text)
    return criteria


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_source(source: str) -> str:
    """Return raw spec text — either from a workspace file or as-is."""
    # Looks like a file path if it has a known extension or is short with no newlines
    looks_like_path = (
        "\n" not in source
        and len(source) < 300
        and any(source.endswith(ext) for ext in (
            ".md", ".txt", ".rst", ".yaml", ".yml",
            ".json", ".toml", ".csv", ".feature",
        ))
    )

    if looks_like_path:
        workspace = Path(CONFIG.WORKSPACE_PATH).resolve()
        target    = (workspace / source).resolve()

        if not str(target).startswith(str(workspace)):
            return f"ERROR: path '{source}' is outside workspace"

        if not target.exists():
            return f"ERROR: spec file not found: {source}"

        if not target.is_file():
            return f"ERROR: '{source}' is a directory"

        size_kb = target.stat().st_size / 1024
        if size_kb > CONFIG.MAX_FILE_SIZE_KB:
            return (
                f"ERROR: spec file too large ({size_kb:.0f} KB). "
                f"Max is {CONFIG.MAX_FILE_SIZE_KB} KB."
            )

        try:
            return target.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"ERROR reading spec file: {e}"

    # Treat as inline text
    return source


def _parse_with_llm(text: str) -> str:
    """Call the configured LLM to extract criteria. Returns JSON string."""
    try:
        # Import here to avoid circular deps at module load time
        from langchain_groq import ChatGroq
        from langchain_core.messages import SystemMessage, HumanMessage
        from core.config import GROQ_API_KEY, GROQ_MODEL

        llm = ChatGroq(
            api_key      = GROQ_API_KEY,
            model        = GROQ_MODEL,
            max_tokens   = 4096,
            streaming    = False,
            model_kwargs = {"include_reasoning": False},
        )

        response = llm.invoke([
            SystemMessage(content=_PARSE_SYSTEM),
            HumanMessage(content=f"Spec text:\n\n{text}"),
        ])

        raw = response.content.strip()

        # Strip accidental markdown fences
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw   = "\n".join(lines[1:-1]) if len(lines) > 2 else raw

        # Validate it parses as JSON array
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return json.dumps({"error": "LLM returned non-array JSON", "raw": raw[:500]})

        # Guarantee all required keys exist with safe defaults
        cleaned = []
        for i, item in enumerate(parsed):
            cleaned.append({
                "id":          item.get("id", f"AC-{i+1:03d}"),
                "description": str(item.get("description", "")),
                "category":    item.get("category", "other"),
                "priority":    item.get("priority", "must"),
                "testable":    bool(item.get("testable", True)),
            })

        return json.dumps(cleaned, indent=2)

    except json.JSONDecodeError as e:
        return json.dumps({"error": f"LLM output was not valid JSON: {e}"})
    except Exception as e:
        return json.dumps({"error": f"Spec parsing failed: {e}"})