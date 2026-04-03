"""
Cross-session project memory — like .cursorrules or CLAUDE.md.
Persists facts about the project across all sessions.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from core.token_usage import estimate_tokens

try:
    from utils.logger import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

_MEMORY_DIR = Path(".code-m8")
_MEMORY_FILE = _MEMORY_DIR / "MEMORY.md"
_DB_FILE = _MEMORY_DIR / "memory.db"

SECTIONS = ["Stack", "Conventions", "Key decisions", "User preferences", "Known issues"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    section   TEXT    NOT NULL,
    fact      TEXT    NOT NULL UNIQUE,
    source    TEXT,
    ts        REAL    DEFAULT (unixepoch()),
    relevance REAL    DEFAULT 1.0,
    access_n  INTEGER DEFAULT 0
);
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts
    USING fts5(fact, section, content=facts, content_rowid=id);
CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, fact, section) VALUES (new.id, new.fact, new.section);
END;
"""


def _conn() -> sqlite3.Connection:
    _MEMORY_DIR.mkdir(exist_ok=True)
    c = sqlite3.connect(_DB_FILE)
    c.executescript(_SCHEMA)
    c.row_factory = sqlite3.Row
    return c


class ProjectMemory:
    def load_md(self) -> dict[str, list[str]]:
        """Parse MEMORY.md into {section: [fact, ...]}"""
        if not _MEMORY_FILE.exists():
            return {s: [] for s in SECTIONS}
        text = _MEMORY_FILE.read_text(encoding="utf-8")
        result: dict[str, list[str]] = {s: [] for s in SECTIONS}
        current = None
        for line in text.splitlines():
            if line.startswith("## "):
                current = line[3:].strip()
            elif line.startswith("- ") and current in result:
                result[current].append(line[2:].strip())
        return result

    def search(self, query: str, top_k: int = 5) -> list[str]:
        """BM25 full-text search over facts."""
        if not query or not query.strip():
            # Return recent facts if no query
            with _conn() as c:
                rows = c.execute(
                    "SELECT fact FROM facts ORDER BY ts DESC LIMIT ?",
                    (top_k,),
                ).fetchall()
            return [r["fact"] for r in rows]

        with _conn() as c:
            try:
                rows = c.execute(
                    "SELECT fact FROM facts_fts WHERE facts_fts MATCH ? ORDER BY rank LIMIT ?",
                    (query, top_k),
                ).fetchall()
                return [r["fact"] for r in rows]
            except Exception:
                # Fallback if FTS fails
                rows = c.execute(
                    "SELECT fact FROM facts ORDER BY ts DESC LIMIT ?",
                    (top_k,),
                ).fetchall()
                return [r["fact"] for r in rows]

    def render_for_context(self, token_budget: int = 800) -> str:
        """Return project memory as a compact string for injection."""
        facts_by_section: dict[str, list[str]] = {}
        with _conn() as c:
            rows = c.execute(
                "SELECT section, fact FROM facts ORDER BY relevance DESC, ts DESC"
            ).fetchall()
        for row in rows:
            facts_by_section.setdefault(row["section"], []).append(row["fact"])

        lines = ["## Project memory"]
        for section in SECTIONS:
            items = facts_by_section.get(section, [])
            if items:
                lines.append(f"\n### {section}")
                for item in items[:10]:
                    lines.append(f"- {item}")

        text = "\n".join(lines)
        if estimate_tokens(text) > token_budget:
            text = text[: token_budget * 4] + "\n...[truncated]"
        return text

    def append(self, section: str, fact: str, source: str = "session") -> bool:
        """Add a fact; silently skip if duplicate."""
        if section not in SECTIONS:
            section = "Key decisions"
        try:
            with _conn() as c:
                c.execute(
                    "INSERT OR IGNORE INTO facts(section, fact, source) VALUES(?,?,?)",
                    (section, fact.strip(), source),
                )
            self._rebuild_md()
            return True
        except Exception as e:
            logger.warning(f"ProjectMemory.append failed: {e}")
            return False

    def fact_exists(self, fact: str) -> bool:
        with _conn() as c:
            row = c.execute(
                "SELECT 1 FROM facts WHERE fact = ?", (fact.strip(),)
            ).fetchone()
        return row is not None

    def _rebuild_md(self) -> None:
        """Regenerate MEMORY.md from DB (single source of truth)."""
        with _conn() as c:
            rows = c.execute(
                "SELECT section, fact FROM facts ORDER BY section, ts"
            ).fetchall()
        lines = ["# Project memory\n"]
        by_section: dict[str, list[str]] = {}
        for row in rows:
            by_section.setdefault(row["section"], []).append(row["fact"])
        for section in SECTIONS:
            if section in by_section:
                lines.append(f"## {section}")
                for fact in by_section[section]:
                    lines.append(f"- {fact}")
                lines.append("")
        _MEMORY_DIR.mkdir(exist_ok=True)
        _MEMORY_FILE.write_text("\n".join(lines), encoding="utf-8")

    def dedup(self) -> int:
        """Remove exact-duplicate facts (case-insensitive)."""
        removed = 0
        with _conn() as c:
            rows = c.execute("SELECT id, lower(fact) AS lf FROM facts").fetchall()
            seen: set[str] = set()
            for row in rows:
                if row["lf"] in seen:
                    c.execute("DELETE FROM facts WHERE id=?", (row["id"],))
                    removed += 1
                else:
                    seen.add(row["lf"])
        if removed:
            self._rebuild_md()
        return removed

    def forget_old(self, max_facts: int = 500) -> int:
        """Evict lowest-relevance facts when over limit."""
        with _conn() as c:
            count = c.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            if count <= max_facts:
                return 0
            to_remove = count - max_facts
            c.execute(
                "DELETE FROM facts WHERE id IN "
                "(SELECT id FROM facts ORDER BY relevance ASC, ts ASC LIMIT ?)",
                (to_remove,),
            )
        self._rebuild_md()
        return to_remove


_project_memory: Optional[ProjectMemory] = None


def get_project_memory() -> ProjectMemory:
    global _project_memory
    if _project_memory is None:
        _project_memory = ProjectMemory()
    return _project_memory
