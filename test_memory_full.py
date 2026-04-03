#!/usr/bin/env python3
"""
Comprehensive Memory System Tests
Tests all memory aspects and identifies issues
"""

import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))


def print_section(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_test(name, passed, details=""):
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"  {status}: {name}")
    if details:
        print(f"       {details}")


# =============================================================================
# TEST 1: Session Storage
# =============================================================================
def test_session_storage():
    """Test that sessions are created and saved correctly"""
    print_section("TEST 1: Session Storage")

    from core.session_manager import create_session, get_session_id, save_turn

    # Create fresh session
    sid = create_session()
    print_test("Session created", sid is not None, f"ID: {sid}")

    # Verify session file exists
    session_file = Path(f"sessions/{sid}.json")
    print_test("Session file created", session_file.exists())

    # Save a turn
    save_turn("test message", [], "test response")

    # Read back
    with open(session_file) as f:
        turns = json.load(f)

    print_test("Turn saved to session", len(turns) == 1)
    print_test("Turn has correct message", turns[0]["user_message"] == "test message")
    print_test("Turn has memory", "memory" in turns[0])

    return sid


# =============================================================================
# TEST 2: Memory Extraction (LLM)
# =============================================================================
def test_memory_extraction():
    """Test that LLM extracts entities from turns"""
    print_section("TEST 2: Memory Extraction")

    from core.session_manager import create_session, save_turn, set_llm_for_extraction
    from core_logic.loop import _qwen_llm

    # Setup LLM for extraction
    if _qwen_llm:
        set_llm_for_extraction(_qwen_llm)

    # Create new session
    sid = create_session()

    # Save turn with code content (correct format)
    test_results = [
        {
            "task": {"agent": "explorer", "instruction": "test"},
            "output": "Created server.js with Express server, Added routes/artworks.js with CRUD endpoints",
            "success": True,
        }
    ]

    save_turn(
        "create a web server with express",
        test_results,
        "Created server.js with Express and routes/artworks.js",
    )

    # Check session file
    with open(f"sessions/{sid}.json") as f:
        turns = json.load(f)

    memory = turns[0].get("memory", {})
    entities = memory.get("entities", {})

    print_test("Memory has entities", len(entities) > 0)
    print_test(
        "Files extracted",
        len(entities.get("files", [])) > 0,
        f"Files: {entities.get('files', [])}",
    )

    return sid


# =============================================================================
# TEST 3: Session Retrieval (load_history)
# =============================================================================
def test_session_retrieval():
    """Test that load_history returns saved turns"""
    print_section("TEST 3: Session Retrieval")

    from core.session_manager import create_session, save_turn, load_history

    sid = create_session()

    # Save multiple turns
    save_turn("message 1", [], "answer 1")
    save_turn("message 2", [], "answer 2")
    save_turn("message 3", [], "answer 3")

    # Load history
    history = load_history(last_n=5)

    print_test("History returns turns", len(history) == 3)
    print_test(
        "History has correct messages", history[0].get("user_message") == "message 1"
    )

    return sid


# =============================================================================
# TEST 4: Compact Memory Generation
# =============================================================================
def test_compact_memory():
    """Test that build_compact_memory works"""
    print_section("TEST 4: Compact Memory")

    from core.session_manager import create_session, save_turn, build_compact_memory

    sid = create_session()

    # Save turns
    for i in range(5):
        save_turn(f"test message {i}", [], f"test response {i}")

    # Build compact memory
    compact = build_compact_memory(recent_turns=3, max_total_chars=1000)

    print_test("Compact memory has rolling_summary", "rolling_summary" in compact)
    print_test("Compact memory has recent_turns", "recent_turns" in compact)
    print_test("Compact memory has files_mentioned", "files_mentioned" in compact)

    return sid


# =============================================================================
# TEST 5: Project Memory (SQLite)
# =============================================================================
def test_project_memory():
    """Test that project memory persists facts"""
    print_section("TEST 5: Project Memory")

    from core.memory import get_project_memory

    pm = get_project_memory()

    # Add a fact
    pm.append("User preferences", "User's name is Nour", source="test")

    # Search for it
    results = pm.search("Nour", top_k=3)
    print_test("Can search project memory", len(results) > 0)
    print_test(
        "Can find user fact", any("Nour" in r for r in results), f"Results: {results}"
    )

    # Check MEMORY.md
    memory_md = Path(".code-m8/MEMORY.md")
    if memory_md.exists():
        content = memory_md.read_text()
        print_test("MEMORY.md exists", "Nour" in content or len(content) > 0)

    return True


# =============================================================================
# TEST 6: Vector Store
# =============================================================================
def test_vector_store():
    """Test that vector store works"""
    print_section("TEST 6: Vector Store")

    from core.memory import get_vector_store

    vs = get_vector_store()

    # Add some text (using upsert method)
    vs.upsert(
        "test_session_1",
        "This is a test about Express server and MongoDB",
        {"source": "test"},
    )
    vs.upsert(
        "test_session_2",
        "Created a web server with Express and routes",
        {"source": "test"},
    )

    # Search
    results = vs.mmr_search("Express MongoDB", top_k=2)
    print_test("Vector store has documents", vs.count() > 0)
    print_test("Vector search returns results", len(results) > 0)

    return True


# =============================================================================
# TEST 7: Memory Index (Session-based)
# =============================================================================
def test_memory_index():
    """Test that MemoryIndex works for session turns"""
    print_section("TEST 7: Memory Index")

    from core.session_manager import create_session, save_turn
    from core.memory.memory_index import MemoryIndex

    sid = create_session()

    # Save turns with content
    save_turn("search for pop logic", [], "Found Stack.pop() method")
    save_turn("search for cache", [], "Found LRUCache implementation")

    # Index the session
    idx = MemoryIndex()
    idx.index_session(sid)

    # Search
    results = idx.search("pop stack")
    print_test("Memory index returns results", len(results) > 0)

    return sid


# =============================================================================
# TEST 8: Retrieval API (retrieve_relevant_memory)
# =============================================================================
def test_retrieval_api():
    """Test the main retrieval function"""
    print_section("TEST 8: Retrieval API")

    from core.session_manager import create_session, save_turn
    from core.memory.retrieval import retrieve_relevant_memory

    sid = create_session()

    # Save meaningful turn
    save_turn("create a web server", [], "Created Express server with MongoDB")

    # Retrieve
    result = retrieve_relevant_memory("what did you create", session_id=sid)

    print_test("Retrieval returns dict", isinstance(result, dict))
    print_test("Retrieval has context", "context" in result)
    print_test("Retrieval has relevant_files", "relevant_files" in result)

    return sid


# =============================================================================
# TEST 9: "What did you do" Query
# =============================================================================
def test_what_did_you_do_query():
    """Test the specific 'what did you do' query that was failing"""
    print_section("TEST 9: 'What did you do' Query")

    from core.session_manager import create_session, save_turn
    from core.memory.retrieval import retrieve_relevant_memory
    from core.memory.memory_manager import get_memory_manager

    sid = create_session()

    # Simulate previous work
    save_turn("create a web server", [], "Created server.js and API routes")
    save_turn("add fancy CSS", [], "Added navbar, hero section, gradient background")
    save_turn("add database", [], "Created MongoDB models for User and Artwork")

    # Now ask "what did you do"
    query = "what did you do"

    # Test retrieval
    result = retrieve_relevant_memory(query, session_id=sid)

    print_test(
        "Query returns results",
        len(result.get("context", {}).get("top_result", {})) > 0
        or len(result.get("relevant_files", [])) > 0,
    )

    # Test MemoryManager build_context
    mm = get_memory_manager()
    ctx = mm.build_context(query, sid)

    print_test("MemoryManager builds context", len(ctx) > 0)
    print_test(
        "Context has content",
        "server" in ctx.lower() or "database" in ctx.lower() or len(ctx) > 50,
        f"Context length: {len(ctx)}",
    )

    return sid


# =============================================================================
# TEST 10: Full Loop Integration Test
# =============================================================================
def test_full_loop():
    """Test the full loop with memory integration"""
    print_section("TEST 10: Full Loop Integration")

    from core.session_manager import create_session
    from core_logic.loop import run_turn

    sid = create_session()

    # Run a turn that should create memory
    try:
        response = run_turn("my name is Nour")
        print_test("First turn runs", True, f"Response: {response[:50]}...")

        # Run second turn asking about name
        response2 = run_turn("what is my name")
        print_test("Second turn runs", True, f"Response: {response2[:50]}...")

        # Check if it remembered
        remembered = "nour" in response2.lower() or "Nour" in response2
        print_test(
            "Memory used in response", remembered, f"Response: {response2[:100]}"
        )

    except Exception as e:
        print_test("Full loop runs", False, str(e)[:100])

    return sid


# =============================================================================
# Main Test Runner
# =============================================================================
def main():
    print("\n" + "=" * 70)
    print("  COMPREHENSIVE MEMORY SYSTEM TESTS")
    print("=" * 70)

    # Run all tests
    test_session_storage()
    time.sleep(0.5)

    test_memory_extraction()
    time.sleep(0.5)

    test_session_retrieval()
    time.sleep(0.5)

    test_compact_memory()
    time.sleep(0.5)

    test_project_memory()
    time.sleep(0.5)

    test_vector_store()
    time.sleep(0.5)

    test_memory_index()
    time.sleep(0.5)

    test_retrieval_api()
    time.sleep(0.5)

    test_what_did_you_do_query()
    time.sleep(0.5)

    test_full_loop()

    print("\n" + "=" * 70)
    print("  TESTS COMPLETE")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
