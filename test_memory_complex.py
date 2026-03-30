#!/usr/bin/env python3
"""
Complex Memory System Test Script
Tests memory retrieval, relationships, and compaction
"""

import sys
import os
import time
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from core_logic.loop import run_turn
from core.session_manager import create_session, get_session_id, save_turn, load_history
from core.memory.memory_index import MemoryIndex
from core.memory.compaction import get_compaction_manager
from context.token_budget import estimate_tokens


def print_section(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def run_test(message: str, wait: float = 2.0) -> str:
    """Send message and get response"""
    print(f"\n>>> USER: {message}")
    try:
        response = run_turn(message)
        print(f"\n>>> AGENT: {response[:400] if response else 'None'}...")
        time.sleep(wait)
        return response
    except Exception as e:
        print(f"\n>>> ERROR: {e}")
        time.sleep(wait)
        return str(e)


def check_memory(session_id: str):
    """Check what's stored in memory"""
    print("\n--- MEMORY CHECK ---")

    # Load session
    session_file = Path("sessions") / f"{session_id}.json"
    if not session_file.exists():
        print("No session file found!")
        return

    turns = json.loads(session_file.read_text())
    print(f"Total turns: {len(turns)}")

    for turn in turns[-4:]:  # Last 4 turns
        mem = turn.get("memory", {})
        rels = mem.get("relationships", {})

        print(f"\n  Turn {turn.get('turn_id')}: {turn.get('user_message', '')[:40]}...")
        print(f"    Intent: {mem.get('intent')}")
        print(f"    Files: {mem.get('entities', {}).get('files', [])[:3]}")
        print(f"    Problems: {mem.get('knowledge', {}).get('problems_found', [])[:2]}")
        print(
            f"    Solutions: {mem.get('knowledge', {}).get('solutions_applied', [])[:2]}"
        )
        print(f"    Relationships: {rels}")

    # Semantic search test
    print("\n--- SEMANTIC SEARCH TEST ---")
    idx = MemoryIndex()
    idx.load_from_session(session_id)

    tests = [
        ("math functions", 2),
        ("cache bug", 2),
        ("subtract", 2),
    ]

    for query, k in tests:
        results = idx.search(query, k=k)
        print(f"\nQuery: '{query}'")
        for r in results:
            print(
                f"  - Turn {r.get('turn_id')}: score={r.get('_similarity_score', 0):.3f}"
            )

    # Files and problems
    print("\n--- FILES & PROBLEMS ---")
    files = idx.get_files_worked_on()
    print(f"Files worked on: {files}")

    ps = idx.get_problems_and_solutions()
    print(f"Problems: {ps.get('problems', [])[:5]}")
    print(f"Solutions: {ps.get('solutions', [])[:5]}")

    # Compaction test
    print("\n--- COMPACTION TEST ---")
    try:
        from core_logic.loop import _qwen_llm

        manager = get_compaction_manager()
        compacted = manager.get_compacted_memory(_qwen_llm, session_id)
        print(f"Total turns: {compacted.get('total_turns')}")
        print(f"Recent turns: {len(compacted.get('recent_turns', []))}")

        l1 = compacted.get("compaction_level_1")
        if l1:
            print(f"\nLevel 1 ({l1.get('turn_count')} turns):")
            print(f"  Summary: {l1.get('summary', '')[:150]}...")
            print(f"  Key files: {l1.get('key_files', [])[:5]}")
    except Exception as e:
        print(f"Compaction check failed: {e}")


def main():
    print("=" * 70)
    print("  COMPLEX MEMORY SYSTEM TEST")
    print("=" * 70)

    # Create fresh session
    create_session()
    session_id = get_session_id()
    print(f"Session ID: {session_id}")

    try:
        # Turn 1: Explore math utils
        print_section("TURN 1: Explore math utils")
        run_test("show me the structure of math utils")

        # Turn 2: Add subtract
        print_section("TURN 2: Add subtract function")
        run_test("add subtract function to math_utils.py")

        # Turn 3: Add divide
        print_section("TURN 3: Add divide function")
        run_test("add divide function")

        # Turn 4: Bug discovery (cache)
        print_section("TURN 4: Bug discovery")
        run_test(
            "there is a bug in cache - when max_size is reached it doesn't properly evict"
        )

        # Turn 5: Fix the bug
        print_section("TURN 5: Fix bug")
        run_test("fix the cache eviction bug")

        # Turn 6: Summary query (should use memory)
        print_section("TURN 6: Summary query - TESTING MEMORY RETRIEVAL")
        run_test("summary what we have done so far", wait=3.0)

        # Turn 7: Cross-reference (cache + math)
        print_section("TURN 7: Cross-reference question")
        run_test("do the math functions we added need caching?", wait=3.0)

        # Turn 8: Add another feature
        print_section("TURN 8: Add multiply function")
        run_test("add multiply function to math_utils")

        # Turn 9: Another summary
        print_section("TURN 9: What did we work on?")
        run_test("what files have we modified?", wait=3.0)

        # Turn 10: Complex reasoning
        print_section("TURN 10: Complex reasoning")
        run_test("what problems did we solve and how?", wait=3.0)

        # Final memory check
        print_section("FINAL MEMORY ANALYSIS")
        check_memory(session_id)

        print("\n" + "=" * 70)
        print("  TEST COMPLETE")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
