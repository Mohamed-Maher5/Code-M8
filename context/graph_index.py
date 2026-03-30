"""Graph indexing for codebase - automatic indexing for coding agent.

This module provides automatic indexing of the workspace codebase into Neo4j.
The coding agent uses this to index code when creating user requests or reading
from the workspace. No user-facing options - fully automatic.
"""

from __future__ import annotations

import hashlib
import os
import time

from context.graph_chunker import chunk_file
from context.graph_config import get_driver, graph_rag_enabled
from context.graph_builder import build_graph, embd_and_store
from context.graph_search import retrieve_code_context
from utils.logger import logger

SKIP_DIRS = {
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
    "sessions",
    "node_modules",
}


# ── Workspace Hash Functions ──────────────────────────────────────────────


def compute_workspace_hash(workspace_root: str) -> str:
    """Compute fast hash of workspace state (paths + mtimes + sizes).

    This is much faster than reading file contents - we only check:
    - File path
    - Modification time
    - File size

    If any of these change, the hash changes → triggers re-index.

    Args:
        workspace_root: Path to workspace directory

    Returns:
        str: MD5 hash representing workspace state
    """
    hash_obj = hashlib.md5()

    for root, dirs, files in os.walk(workspace_root):
        # Skip ignored directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        # Sort for consistent ordering across platforms
        for file in sorted(files):
            if not file.endswith(".py"):
                continue

            file_path = os.path.join(root, file)
            try:
                stat = os.stat(file_path)
                # Combine: path + modification time + size
                # This changes if file is added, deleted, or modified
                info = f"{file_path}:{stat.st_mtime}:{stat.st_size}"
                hash_obj.update(info.encode())
            except OSError:
                continue

    return hash_obj.hexdigest()


def _get_stored_hash(driver) -> str:
    """Get stored workspace hash from graph DB.

    Returns:
        str: Previously stored hash, or None if first time
    """
    with driver.session() as session:
        result = session.run("""
            MATCH (m:Metadata {key: 'workspace_hash'})
            RETURN m.hash AS hash
        """)
        record = result.single()
        return record["hash"] if record else None


def _has_indexed_chunks(driver) -> bool:
    """Check if workspace has indexed chunks in Neo4j.

    Returns:
        bool: True if chunks exist, False otherwise
    """
    with driver.session() as session:
        result = session.run("""
            MATCH (c:Chunk)
            RETURN count(c) as count
        """)
        record = result.single()
        chunk_count = record["count"] if record else 0
        return chunk_count > 0


def _save_hash(driver, hash_value: str) -> None:
    """Save workspace hash to graph DB for future comparison.

    Args:
        driver: Neo4j driver
        hash_value: Current workspace hash
    """
    with driver.session() as session:
        session.run(
            """
            MERGE (m:Metadata {key: 'workspace_hash'})
            SET m.hash = $hash, m.updated_at = timestamp()
        """,
            hash=hash_value,
        )


def _get_file_stored_hash(file_path, driver):
    """Get the stored MD5 hash for a specific file node in graph DB."""
    with driver.session() as session:
        result = session.run(
            "MATCH (f:File {path: $path}) RETURN f.last_parsed_hash AS h",
            path=file_path,
        )
        record = result.single()
        return record["h"] if record else None


def index_codebase(path: str, driver) -> tuple[int, int]:
    """Walk workspace, chunk changed .py files, merge into graph, embed.

    Returns:
        tuple[int, int]: (files_indexed, chunks_total)
    """
    path = os.path.abspath(path)
    all_chunks = []
    all_file_nodes = []
    files_touched = 0

    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for file in files:
            if not file.endswith(".py"):
                continue
            file_path = os.path.join(root, file)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except OSError:
                continue
            current_hash = hashlib.md5(content.encode()).hexdigest()
            stored_hash = _get_file_stored_hash(file_path, driver)
            if stored_hash == current_hash:
                continue
            chunks, file_node = chunk_file(file_path)
            if not chunks or file_node is None:
                continue

            # Normalize paths to absolute form to match Neo4j format
            # This fixes path mismatch issues like ./workspace/file.py vs /abs/path/file.py
            abs_file_path = os.path.abspath(file_path)
            for c in chunks:
                if c.name.startswith("./"):
                    # Convert ./relative/path:name to /abs/path:name
                    parts = c.name.split(":")
                    rel_part = parts[0][2:]  # Remove ./
                    abs_part = os.path.abspath(rel_part)
                    c.name = abs_part + ":" + ":".join(parts[1:])

            all_chunks.extend(chunks)
            all_file_nodes.append(file_node)
            files_touched += 1

    if not all_chunks:
        return 0, 0

    build_graph(all_chunks, all_file_nodes, driver)
    embd_and_store(all_chunks, driver)
    return files_touched, len(all_chunks)


def index_workspace(workspace_root: str) -> str:
    """Index workspace for the coding agent.

    This is called automatically by the coding agent when:
    - Creating a user request
    - Reading codebase from workspace

    Returns:
        str: Status message about indexing result
    """
    if not graph_rag_enabled():
        return (
            "Graph RAG is not configured. Set NEO4J_URI, NEO4J_USERNAME, and "
            "NEO4J_PASSWORD in your .env (Neo4j 5.x with vector indexes)."
        )
    driver = get_driver()
    if driver is None:
        return "Could not connect to Neo4j."
    try:
        n_files, n_chunks = index_codebase(workspace_root, driver)
        if n_files == 0:
            return "Graph index: no new or changed .py files to index (or workspace empty)."
        return f"Graph index: indexed {n_files} file(s), {n_chunks} chunk(s) written."
    except Exception as e:
        return f"Graph index failed: {e}"


def clear_graph_index() -> str:
    """Clear all nodes from the graph database.

    Used internally when a full re-index is needed or when workspace
    is significantly restructured.
    """
    if not graph_rag_enabled():
        return "Neo4j not configured."
    driver = get_driver()
    if driver is None:
        return "Could not connect to Neo4j."
    try:
        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        return "Graph index cleared (all nodes removed)."
    except Exception as e:
        return f"Clear failed: {e}"


def cleanup_orphaned_chunks(driver) -> int:
    """Remove Chunk nodes that are not referenced by any File.

    Returns:
        int: Number of orphaned chunks deleted
    """
    with driver.session() as session:
        # Find chunks not connected to any File
        result = session.run("""
            MATCH (c:Chunk)
            WHERE NOT EXISTS {
                MATCH (f:File)-[:CONTAINS]->(c)
            }
            DETACH DELETE c
        """)
        deleted = result.consume().counters.nodes_deleted
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} orphaned chunks")
        return deleted


def cleanup_orphaned_files(driver, workspace_root: str) -> int:
    """Remove File nodes for files that no longer exist in workspace.

    Args:
        driver: Neo4j driver
        workspace_root: Path to workspace to check against

    Returns:
        int: Number of orphaned files deleted
    """
    # Get all .py files that actually exist
    existing_files = set()
    for root, dirs, files in os.walk(workspace_root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for file in files:
            if file.endswith(".py"):
                existing_files.add(os.path.join(root, file))

    # Find and delete File nodes for non-existent files
    with driver.session() as session:
        result = session.run(
            """
            MATCH (f:File)
            WHERE NOT f.path IN $existing_files
            DETACH DELETE f
        """,
            existing_files=list(existing_files),
        )

        deleted = result.consume().counters.nodes_deleted
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} orphaned files")
        return deleted


def auto_cleanup(workspace_root: str) -> dict:
    """Automatic cleanup of orphaned and stale data.

    This should be called periodically (e.g., once per session) to:
    1. Remove chunks not referenced by any file
    2. Remove files that no longer exist in workspace
    3. Remove stale metadata

    Args:
        workspace_root: Path to workspace

    Returns:
        dict: Cleanup statistics
    """
    if not graph_rag_enabled():
        return {"status": "disabled"}

    driver = get_driver()
    if driver is None:
        return {"status": "error", "message": "Could not connect to Neo4j"}

    try:
        stats = {
            "status": "success",
            "orphaned_chunks": 0,
            "orphaned_files": 0,
        }

        # Cleanup orphaned chunks
        stats["orphaned_chunks"] = cleanup_orphaned_chunks(driver)

        # Cleanup orphaned files
        stats["orphaned_files"] = cleanup_orphaned_files(driver, workspace_root)

        logger.info(f"Cleanup complete: {stats}")
        return stats

    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        return {"status": "error", "message": str(e)}


def query_context(question: str, k: int = 5) -> str:
    """Retrieval-only: code context string for coding agent.

    This is used internally by the coding agent tools for semantic search.

    Args:
        question: The search query
        k: Number of initial chunks to retrieve

    Returns:
        str: Context retrieved from Neo4j graph
    """
    if not graph_rag_enabled():
        return "Graph RAG not configured. Set NEO4J_URI, NEO4J_USERNAME, and NEO4J_PASSWORD in .env"

    driver = get_driver()
    if driver is None:
        return "Could not connect to Neo4j. Check your credentials."

    try:
        return retrieve_code_context(question, driver, k=k)
    except Exception as e:
        return f"Graph search failed: {e}"


def ensure_indexed(workspace_root: str) -> bool:
    """Ensure workspace is indexed, skipping if unchanged.

    This is the main entry point for the coding agent - it will automatically
    index the workspace if needed. Uses workspace hash to detect changes,
    making subsequent requests much faster when codebase is unchanged.

    Flow:
    1. Compute current workspace hash (fast - metadata only)
    2. Compare with stored hash from graph DB
    3. If match → skip indexing (0.1s) + auto-cleanup
    4. If different → incremental index (1-10s) + cleanup

    Args:
        workspace_root: Path to workspace directory

    Returns:
        bool: True if indexing was performed or already up-to-date, False if failed
    """
    if not graph_rag_enabled():
        return False

    driver = get_driver()
    if driver is None:
        return False

    try:
        # Step 1: Compute current workspace hash (fast)
        current_hash = compute_workspace_hash(workspace_root)

        # Step 2: Get stored hash from graph DB
        stored_hash = _get_stored_hash(driver)

        # Step 3: Check if hash matches AND chunks exist
        if stored_hash == current_hash:
            # Hash matches - but verify chunks actually exist
            if _has_indexed_chunks(driver):
                # Chunks exist - workspace properly indexed
                logger.info(
                    f"Workspace hash unchanged: {current_hash[:8]}, chunks verified"
                )
                return True
            else:
                # Hash matches but NO chunks! Index was corrupted/cleared - re-index
                logger.warning(
                    "Workspace hash matches but no chunks found - re-indexing required"
                )
        else:
            # Step 4: Hash differs - index workspace
            logger.info(
                "Workspace changed: %s -> %s",
                stored_hash[:8] if stored_hash else "None",
                current_hash[:8],
            )

        # Index the workspace
        index_workspace(workspace_root)

        # Step 5: Save new hash for next time
        _save_hash(driver, current_hash)

        # Step 6: Verify indexing worked
        if not _has_indexed_chunks(driver):
            logger.error("Indexing completed but no chunks found in database!")

        # Step 7: Cleanup orphaned data after indexing
        auto_cleanup(workspace_root)

        return True

    except Exception as e:
        logger.error(f"Index failed: {e}")
        return False
