#!/usr/bin/env python3
"""
Memory System Test Script
Tests the conversation memory of Code-M8
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from core_logic.loop import run_turn
from core.session_manager import create_session, get_session_id, save_turn, load_history
from context.token_budget import estimate_tokens


def print_section(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def run_test(message: str) -> str:
    """Send message and get response"""
    print(f"\n>>> USER: {message}")
    response = run_turn(message)
    print(f"\n>>> AGENT: {response[:500]}...")
    return response


def test_phase_1_short_term_memory():
    """Phase 1: Short-Term Memory Test"""
    print_section("PHASE 1: SHORT-TERM MEMORY")

    # Create fresh session
    create_session()
    print(f"Session ID: {get_session_id()}")

    # Turn 1: Introduce facts
    run_test("My name is Nour and I am building a coding agent.")

    # Turn 2: More facts
    run_test("I prefer Python and hate Java.")

    # Turns 3-12: Unrelated messages
    for i in range(10):
        run_test(
            f"This is unrelated message number {i}. Tell me what you think about debugging."
        )

    # Test recall
    print("\n--- TEST: What is my name? ---")
    response = run_test("What is my name?")
    assert "Nour" in response, "FAILED: Did not remember name"

    print("\n--- TEST: What language do I prefer? ---")
    response = run_test("What language do I prefer?")
    assert "Python" in response, "FAILED: Did not remember Python preference"

    print("\n✅ PHASE 1 PASSED")


def test_phase_2_long_term_memory():
    """Phase 2: Long-Term Memory Test"""
    print_section("PHASE 2: LONG-TERM MEMORY")

    # Use existing session from Phase 1
    print(f"Session ID: {get_session_id()}")

    # Turn: Introduce new facts
    run_test("I am working on a BI agent using SQL and MongoDB.")
    run_test("My GPU has 8GB VRAM.")

    # Different topic
    run_test("Tell me about file search algorithms.")
    run_test("How does vector embedding work?")

    # Test long-term recall
    print("\n--- TEST: What am I building? ---")
    response = run_test("What am I building?")
    print(
        f"Response mentions BI: {'BI' in response or 'business intelligence' in response.lower()}"
    )
    print(f"Response mentions SQL: {'SQL' in response}")

    print("\n--- TEST: What are my hardware limits? ---")
    response = run_test("What are my hardware limits?")
    print(f"Response mentions 8GB: {'8' in response}")


def test_phase_3_distraction_noise():
    """Phase 3: Distraction & Noise Test"""
    print_section("PHASE 3: DISTRACTION & NOISE")

    # Insert noise
    run_test("The quick brown fox jumps over the lazy dog. 123456789 random numbers.")
    run_test("""
    def complicated_function(x, y, z):
        # This is a noise function
        result = 0
        for i in range(x):
            result += y * z
            if result > 1000000:
                break
        return result
    """)
    run_test("xkcdflkjsd flkjds lkfjds lkfjdslkfj dsflkjsd flkjds")

    # Test recall
    print("\n--- TEST: What do I prefer: Python or Java? ---")
    response = run_test("What do I prefer: Python or Java?")
    print(f"Response: {response[:200]}")


def test_phase_4_memory_persistence():
    """Phase 4: Memory Persistence Test"""
    print_section("PHASE 4: MEMORY PERSISTENCE")

    # Check session file
    import json
    from pathlib import Path
    from core.config import SESSIONS_PATH

    session_id = get_session_id()
    session_file = Path(SESSIONS_PATH) / f"{session_id}.json"

    if session_file.exists():
        turns = json.loads(session_file.read_text())
        print(f"Session has {len(turns)} turns persisted")

        # Check memory content
        last_turn = turns[-1] if turns else {}
        memory = last_turn.get("memory", {})
        print(f"Last turn memory: {list(memory.keys())}")

    # Simulate restart by asking
    print("\n--- TEST: Do you remember my project? ---")
    response = run_test("Do you remember what project I'm working on?")
    print(f"Response: {response[:300]}")


def test_phase_5_semantic_retrieval():
    """Phase 5: Semantic Retrieval Test"""
    print_section("PHASE 5: SEMANTIC RETRIEVAL")

    # Introduce semantic info
    run_test("I like lightweight coding models.")
    run_test("Efficiency matters more than raw power.")

    # Later ask with different wording
    print("\n--- TEST: What type of models do I prefer? ---")
    response = run_test("What type of models do I prefer?")
    print(f"Response: {response[:300]}")


def test_phase_6_contradiction():
    """Phase 6: Contradiction Handling"""
    print_section("PHASE 6: CONTRADICTION HANDLING")

    # State preference
    run_test("I prefer Python.")

    # Contradict
    run_test("Actually I now prefer C++.")

    # Test which is remembered
    print("\n--- TEST: What language do I prefer now? ---")
    response = run_test("What language do I prefer?")
    print(f"Response: {response[:300]}")


def test_phase_7_context_compression():
    """Phase 7: Context Compression"""
    print_section("PHASE 7: CONTEXT COMPRESSION")

    # Many turns
    for i in range(5):
        run_test(f"Turn {i}: Tell me about Python decorators.")
        run_test(f"Turn {i}: Explain list comprehensions.")

    # Summary test
    print("\n--- TEST: Summarize what you know about me ---")
    response = run_test("Summarize what you know about me.")
    print(f"Response: {response[:500]}")


def main():
    print("=" * 70)
    print("  CODE-M8 MEMORY SYSTEM TEST SUITE")
    print("=" * 70)

    try:
        test_phase_1_short_term_memory()
        test_phase_2_long_term_memory()
        test_phase_3_distraction_noise()
        test_phase_4_memory_persistence()
        test_phase_5_semantic_retrieval()
        test_phase_6_contradiction()
        test_phase_7_context_compression()

        print("\n" + "=" * 70)
        print("  ALL TESTS COMPLETED")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
