#!/usr/bin/env python3
"""
Comprehensive Memory System QA Test
Tests all 8 phases of memory functionality
"""

import sys
import os
import time
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from core_logic.loop import run_turn
from core.session_manager import create_session, get_session_id
from core.memory.memory_index import MemoryIndex
from core.memory.compaction import get_compaction_manager
from core.memory import get_project_memory, get_vector_store
from core_logic.loop import _qwen_llm


def print_section(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def run_test(message: str, wait: float = 1.0) -> str:
    """Send message and get response"""
    print(f"\n>>> USER: {message}")
    try:
        response = run_turn(message)
        print(f"\n>>> AGENT: {response[:300] if response else 'None'}...")
        time.sleep(wait)
        return response
    except Exception as e:
        print(f"\n>>> ERROR: {e}")
        time.sleep(wait)
        return str(e)


def check_memory(session_id: str):
    """Check what's stored in memory"""
    session_file = Path("sessions") / f"{session_id}.json"
    if not session_file.exists():
        print("No session file found!")
        return

    turns = json.loads(session_file.read_text())
    print(f"\nTotal turns: {len(turns)}")

    for turn in turns[-3:]:
        mem = turn.get("memory", {})
        entities = mem.get("entities", {})
        knowledge = mem.get("knowledge", {})

        print(f"\n  Turn {turn.get('turn_id')}: {turn.get('user_message', '')[:40]}...")
        print(f"    Files: {entities.get('files', [])[:3]}")
        print(f"    Classes: {entities.get('classes', [])[:3]}")
        print(f"    Problems: {knowledge.get('problems_found', [])[:2]}")
        print(f"    Solutions: {knowledge.get('solutions_applied', [])[:2]}")

    # Check vector store
    vs = get_vector_store()
    print(f"\n  Vector store: {vs.count()} items")

    # Check project memory
    pm = get_project_memory()
    print(f"  Project memory: {pm.search('')}")


def test_phase_1_short_term_memory():
    """Phase 1: Short-Term Memory Test"""
    print_section("PHASE 1: SHORT-TERM MEMORY")

    create_session()
    session_id = get_session_id()
    print(f"Session ID: {session_id}")

    # Turn 1: Introduce facts
    run_test("My name is Nour and I am building a coding agent.")

    # Turn 2: More facts
    run_test("I prefer Python and hate Java.")

    # Turns 3-7: Unrelated messages
    for i in range(5):
        run_test(f"This is unrelated message {i}. Tell me about debugging.")

    # Test recall
    print("\n" + "=" * 50)
    print("TEST: What is my name?")
    response = run_test("What is my name?", wait=2.0)

    print("\nTEST: What language do I prefer?")
    response2 = run_test("What language do I prefer?", wait=2.0)

    # Check if recalled correctly
    name_correct = "Nour" in response or "nour" in response.lower()
    lang_correct = "Python" in response2

    print(
        f"\n>>> RESULT: Name recalled: {name_correct}, Language recalled: {lang_correct}"
    )

    return name_correct and lang_correct


def test_phase_2_long_term_memory():
    """Phase 2: Long-Term Memory Test"""
    print_section("PHASE 2: LONG-TERM MEMORY")

    session_id = get_session_id()
    print(f"Using session: {session_id}")

    # Introduce new facts
    run_test("I am working on a BI agent using SQL and MongoDB.")
    run_test("My GPU has 8GB VRAM.")

    # Different topic
    run_test("Tell me about file search algorithms.")
    run_test("How does vector embedding work?")

    # Test long-term recall
    print("\n" + "=" * 50)
    print("TEST: What am I building?")
    response = run_test("What am I building?", wait=2.0)

    print("\nTEST: What are my hardware limits?")
    response2 = run_test("What are my hardware limits?", wait=2.0)

    bi_correct = "BI" in response or "business intelligence" in response.lower()
    gpu_correct = "8" in response2 or "GB" in response2

    print(f"\n>>> RESULT: BI recalled: {bi_correct}, GPU recalled: {gpu_correct}")

    return bi_correct and gpu_correct


def test_phase_3_distraction():
    """Phase 3: Distraction & Noise Test"""
    print_section("PHASE 3: DISTRACTION & NOISE")

    # Insert noise
    run_test("The quick brown fox jumps over the lazy dog. 123456789 random numbers.")
    run_test("def complicated_function(x): return sum(x)")
    run_test("xkcdflkjsd flkjds lkfjds")

    # Test recall
    print("\n" + "=" * 50)
    print("TEST: What do I prefer: Python or Java?")
    response = run_test("What do I prefer: Python or Java?", wait=2.0)

    python_correct = "Python" in response and "Java" not in response

    print(f"\n>>> RESULT: Correct preference recalled: {python_correct}")

    return python_correct


def test_phase_4_persistence():
    """Phase 4: Memory Persistence Test"""
    print_section("PHASE 4: MEMORY PERSISTENCE")

    session_id = get_session_id()

    # Check session file
    session_file = Path("sessions") / f"{session_id}.json"
    turns = json.loads(session_file.read_text())
    print(f"Session has {len(turns)} turns persisted")

    # Simulate restart - just query without history
    print("\n" + "=" * 50)
    print("TEST: Do you remember my project?")
    response = run_test("Do you remember what project I'm working on?", wait=2.0)

    # Check if response mentions any past work
    has_memory = len(response) > 50 and (
        "agent" in response.lower()
        or "building" in response.lower()
        or "BI" in response
    )

    print(f"\n>>> RESULT: Has persistent memory: {has_memory}")

    return has_memory


def test_phase_5_semantic():
    """Phase 5: Semantic Retrieval Test"""
    print_section("PHASE 5: SEMANTIC RETRIEVAL")

    # Introduce semantic info
    run_test("I like lightweight coding models.")
    run_test("Efficiency matters more than raw power.")

    # Later ask with different wording
    print("\n" + "=" * 50)
    print("TEST: What type of models do I prefer?")
    response = run_test("What type of models do I prefer?", wait=2.0)

    # Should find semantic match
    lightweight_correct = (
        "lightweight" in response.lower() or "efficient" in response.lower()
    )

    print(f"\n>>> RESULT: Semantic retrieval: {lightweight_correct}")

    return lightweight_correct


def test_phase_6_contradiction():
    """Phase 6: Contradiction Handling"""
    print_section("PHASE 6: CONTRADICTION HANDLING")

    # State preference
    run_test("I prefer Python.")

    # Contradict
    run_test("Actually I now prefer C++.")

    # Test which is remembered
    print("\n" + "=" * 50)
    print("TEST: What language do I prefer now?")
    response = run_test("What language do I prefer?", wait=2.0)

    # Should use latest info (C++)
    c_plus_correct = "C++" in response or "c++" in response.lower()

    print(f"\n>>> RESULT: Updated preference: {c_plus_correct}")

    return c_plus_correct


def test_phase_7_compression():
    """Phase 7: Context Compression"""
    print_section("PHASE 7: CONTEXT COMPRESSION")

    # Many turns
    for i in range(5):
        run_test(f"Tell me about Python decorators {i}.")
        run_test(f"Explain list comprehensions {i}.")

    # Summary test
    print("\n" + "=" * 50)
    print("TEST: Summarize what you know about me")
    response = run_test("Summarize what you know about me.", wait=2.0)

    # Should be concise and accurate
    has_summary = len(response) < 500 and len(response) > 50

    print(f"\n>>> RESULT: Compression working: {has_summary}")

    return has_summary


def test_phase_8_code_memory():
    """Phase 8: Code Memory Test"""
    print_section("PHASE 8: CODE MEMORY")

    # Create code
    run_test("Create a function called add that adds two numbers")

    # Later ask
    print("\n" + "=" * 50)
    print("TEST: What function did I write earlier?")
    response = run_test("What function did I write earlier?", wait=2.0)

    # Should recall function
    has_code_memory = "add" in response.lower() or "function" in response.lower()

    print(f"\n>>> RESULT: Code memory: {has_code_memory}")

    return has_code_memory


def main():
    print("=" * 70)
    print("  COMPREHENSIVE MEMORY SYSTEM QA TEST")
    print("=" * 70)

    results = {}

    try:
        results["Phase 1"] = test_phase_1_short_term_memory()
        results["Phase 2"] = test_phase_2_long_term_memory()
        results["Phase 3"] = test_phase_3_distraction()
        results["Phase 4"] = test_phase_4_persistence()
        results["Phase 5"] = test_phase_5_semantic()
        results["Phase 6"] = test_phase_6_contradiction()
        results["Phase 7"] = test_phase_7_compression()
        results["Phase 8"] = test_phase_8_code_memory()

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()

    # Final memory check
    print_section("FINAL MEMORY ANALYSIS")
    check_memory(get_session_id())

    # Summary
    print("\n" + "=" * 70)
    print("  TEST RESULTS SUMMARY")
    print("=" * 70)

    total = 0
    passed = 0
    for phase, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{phase}: {status}")
        total += 1
        if result:
            passed += 1

    print(f"\nTotal: {passed}/{total} passed ({passed / total * 100:.0f}%)")

    return results


if __name__ == "__main__":
    main()
