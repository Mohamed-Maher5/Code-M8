# core_logic/loop.py
# Main turn engine — loads workspace, runs agents, returns response to UI
#
# Each turn:
#     1. orchestrator.plan()        → Plan
#     2. dispatcher.run_plan()      → List[TaskResult]
#     3. synthesizer.synthesize()   → final answer string
#     4. Return string to terminal_ui
#
# ESC Key Interrupt:
#   - Checks ui.interrupt.is_interrupted() between each step
#   - If interrupted, raises ui.interrupt.InterruptError
#   - terminal_ui catches this and returns to prompt gracefully

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq

from agents.coder import Coder
from agents.explorer import Explorer
from agents.orchestrator import Orchestrator
from core.config import (
    HUNTER_MODEL,
    MINIMAX_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    GROQ_API_KEY,
    GROQ_MODEL,
    GROQ_MAX_OUTPUT_TOKENS,
    PLANNING_CONTEXT_MAX_TOKENS,
    PLANNING_CONTEXT_MAX_CHARS,
    EXPLORER_MAX_STEPS,
)
from core.token_usage import estimate_tokens
from core_logic.dispatcher import Dispatcher
from core_logic.synthesizer import Synthesizer
from core_logic.planner import validate_plan, print_plan, plan_summary, fallback_plan
from core.token_usage import record_usage
from utils.logger import logger
from ui.interrupt import is_interrupted, InterruptError

# =============================================================================
# CHANGED: 2026-03-29 - Updated imports for new session_manager functions
# Purpose: Support structured history with file tracking (Option B)
# =============================================================================
from core.session_manager import (
    save_turn,
    load_history,
    _format_turn,
    _build_chat_context,
    build_compact_memory,
    build_llm_compacted_memory,
    set_llm_for_extraction,
    get_session_id,
)

# NEW: Enhanced memory imports
try:
    from core.memory.retrieval import (
        retrieve_relevant_memory,
        build_memory_context_for_orchestrator,
        get_session_memory_summary,
    )
    from core.memory.memory_manager import get_memory_manager

    ENHANCED_MEMORY = True
    _memory_manager = get_memory_manager()
except ImportError:
    ENHANCED_MEMORY = False
    _memory_manager = None
    print("[LOOP DEBUG] Enhanced memory not available")


# ── Status helper ─────────────────────────────────────────────────────────────


def _set_status(agent: str, action: str) -> None:
    try:
        from core.agent_status import set_agent

        set_agent(agent, action)
    except ImportError:
        pass


# ── LLM clients ───────────────────────────────────────────────────────────────

_hunter_llm = ChatOpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url=OPENROUTER_BASE_URL,
    model=MINIMAX_MODEL,
    streaming=True,
)

_qwen_llm = ChatGroq(
    api_key=GROQ_API_KEY,
    max_tokens=GROQ_MAX_OUTPUT_TOKENS,
    model=GROQ_MODEL,
    streaming=True,
    model_kwargs={"include_reasoning": False},
)


# ── Agents ────────────────────────────────────────────────────────────────────

_orchestrator = Orchestrator(llm=_qwen_llm)
_explorer = Explorer(llm=_qwen_llm)
_coder = Coder(llm=_hunter_llm)

_dispatcher = Dispatcher(
    orchestrator=_orchestrator,
    explorer=_explorer,
    coder=_coder,
)

_synthesizer = Synthesizer(orchestrator=_orchestrator)

# Setup LLM for memory extraction
try:
    set_llm_for_extraction(_qwen_llm)
except Exception as e:
    print(f"[LOOP] Could not setup LLM extraction: {e}")


# ── Session history ───────────────────────────────────────────────────────────

_PLANNING_CONTEXT_BUDGET_CHARS = PLANNING_CONTEXT_MAX_CHARS
_PLANNING_CONTEXT_BUDGET_TOKENS = PLANNING_CONTEXT_MAX_TOKENS


# ── Main turn engine ──────────────────────────────────────────────────────────


def run_turn(user_input: str) -> str:
    logger.info(f"Turn started: {user_input}")

    # NEW: Initialize file tracking for this turn
    try:
        from core.agent_file_tracker import reset_tracker, init_file_tracking

        reset_tracker()
        init_file_tracking()
    except ImportError:
        pass

    # =============================================================================
    # CHANGED: 2026-03-29 - Load structured history (Option B - Better Context)
    #   - Returns list of dicts instead of flat strings
    #   - Includes files_mentioned per turn
    #   - Reduced from last_n=5 to last_n=3 for cleaner context
    # =============================================================================
    history = load_history(last_n=6, max_chars=700)

    # step 0 — classify
    message_type = _classify(user_input)
    logger.info(f"Message type: {message_type}")

    if message_type == "chat":
        # =============================================================================
        # CHANGED: 2026-03-30 - Add memory retrieval for chat queries
        # CHANGED: 2026-03-31 - Make memory detection generic via classifier
        # =============================================================================
        base_context = _build_chat_context(history)

        # For all chat messages, try to get relevant memory context
        # The classifier already determines if it's a memory-dependent query (chat type)
        if ENHANCED_MEMORY:
            try:
                from core.memory.retrieval import retrieve_relevant_memory
                from core.session_manager import get_session_id
                from core.memory.memory_manager import get_memory_manager

                session_id = get_session_id()
                if session_id:
                    # Use MemoryManager for project-level context
                    mm = get_memory_manager()
                    memory_context = mm.build_context(user_input, session_id)

                    # Also get semantic search results with proper formatting
                    from core.memory.retrieval import (
                        build_memory_context_for_orchestrator,
                    )

                    memory_context += build_memory_context_for_orchestrator(
                        user_input, session_id=session_id
                    )

                    # Get raw retrieval for files list
                    memory_result = retrieve_relevant_memory(
                        user_input, session_id=session_id
                    )
                    relevant_files = memory_result.get("relevant_files", [])
                    top_result = memory_result.get("context", {}).get("top_result", {})
                    summary = top_result.get("entities_summary", "")

                    # Add summary if not already in context
                    if summary and summary not in memory_context:
                        memory_context += f"\n\n=== Previous Work Summary ===\n{summary}\n\nFiles: {', '.join(relevant_files[:5])}"

                    if memory_context:
                        base_context = memory_context + "\n\n" + base_context
                        print(
                            f"[CHAT MEMORY] Added memory context - {len(relevant_files)} files"
                        )
            except Exception as e:
                print(f"[CHAT MEMORY] Failed to retrieve memory: {e}")

        # Get response from chat
        chat_response = _chat_reply(user_input, base_context)

        # Save turn for chat messages too
        save_turn(
            user_message=user_input,
            all_results=[],
            final_answer=chat_response,
        )

        return chat_response

    # =============================================================================
    # CHANGED: 2026-03-29 - Build rich context string for orchestrator
    #   - Includes recent files touched across all turns
    #   - Uses _format_turn() for better formatting
    # =============================================================================
    print("\n" + "=" * 80)
    print("[LOOP DEBUG] ══ MAIN TURN LOOP ══")
    print(f"  User input: {user_input[:80]}{'...' if len(user_input) > 80 else ''}")
    print(f"  Message type: {message_type}")
    print(f"  History length: {len(history)} messages")
    print("=" * 80)

    print("\n[LOOP DEBUG] Calling build_compact_memory()...")

    # Try LLM-compacted memory first (more intelligent)
    if ENHANCED_MEMORY:
        try:
            llm_compacted = build_llm_compacted_memory()
            if llm_compacted.get("method") == "llm" and llm_compacted.get(
                "llm_compacted"
            ):
                # Use LLM-compacted version
                compact_memory = {
                    "rolling_summary": llm_compacted.get("llm_compacted", ""),
                    "recent_turns": [],
                    "files_mentioned": [],
                }
                print("[LOOP DEBUG] Using LLM-compacted memory")
            else:
                compact_memory = build_compact_memory(
                    recent_turns=4,
                    max_total_chars=_PLANNING_CONTEXT_BUDGET_CHARS,
                    per_turn_chars=700,
                )
        except Exception as e:
            print(f"[LOOP DEBUG] LLM compaction failed: {e}")
            compact_memory = build_compact_memory(
                recent_turns=4,
                max_total_chars=_PLANNING_CONTEXT_BUDGET_CHARS,
                per_turn_chars=700,
            )
    else:
        compact_memory = build_compact_memory(
            recent_turns=4,
            max_total_chars=_PLANNING_CONTEXT_BUDGET_CHARS,
            per_turn_chars=700,
        )

    print("[LOOP DEBUG] Calling _build_planning_context()...")
    history_context = _build_planning_context(
        compact_memory, history, user_request=user_input
    )

    # NEW: Add semantic memory retrieval for planning
    if ENHANCED_MEMORY:
        try:
            from core.memory.retrieval import retrieve_relevant_memory
            from core.session_manager import get_session_id

            session_id = get_session_id()
            if session_id:
                memory_result = retrieve_relevant_memory(
                    user_input, session_id=session_id
                )

                relevant_files = memory_result.get("relevant_files", [])
                top_result = memory_result.get("context", {}).get("top_result", {})
                summary = top_result.get("entities_summary", "")

                if summary or relevant_files:
                    memory_context = f"""

=== SESSION MEMORY (from previous work) ===
{summary}

Files involved in related work: {", ".join(relevant_files[:5]) if relevant_files else "None"}
========================================
"""
                    history_context += memory_context
                    print(
                        f"[PLANNING MEMORY] Added {len(relevant_files)} relevant files"
                    )
        except Exception as e:
            print(f"[PLANNING MEMORY] Failed: {e}")

    # step 1 — orchestrator plans using enriched session history
    _set_status("orchestrator", "planning")
    try:
        plan = _orchestrator.plan(
            user_request=user_input,
            session_history=[history_context],
        )
    except Exception as e:
        logger.error(f"Plan error: {e}")
        return f"Could not build a plan: {e}"

    # Check for ESC interrupt after planning
    if is_interrupted():
        logger.info("Turn interrupted after planning")
        raise InterruptError("Interrupted by user")

    # validate and print plan
    if not validate_plan(plan):
        plan = fallback_plan(user_input)

    print_plan(plan)
    logger.info(f"Plan: {plan_summary(plan)}")

    # step 2 — dispatch
    _set_status("explorer", "exploring")
    try:
        all_results = _dispatcher.run_plan(
            plan=plan,
            orchestrator=_orchestrator,
            user_request=user_input,
            max_steps=EXPLORER_MAX_STEPS,
        )
    except InterruptError:
        raise  # Re-raise interrupt errors
    except Exception as e:
        logger.error(f"Dispatch error: {e}")
        _set_status("coder", "coding")
        return f"Agent error: {e}"

    # Check for ESC interrupt after dispatch
    if is_interrupted():
        logger.info("Turn interrupted after dispatch")
        raise InterruptError("Interrupted by user")

    # step 3 — synthesize
    _set_status("orchestrator", "responding")
    response = _synthesizer.synthesize(
        user_request=user_input,
        all_results=all_results,
    )
    save_turn(
        user_message=user_input,
        all_results=all_results,
        final_answer=response,
    )

    # NEW: Persist memory via MemoryManager
    if _memory_manager is not None and ENHANCED_MEMORY:
        try:
            from core.memory.llm_extractor import extract_with_llm

            llm_memory = extract_with_llm(_qwen_llm, user_input, all_results, response)
            _memory_manager.on_turn_end(user_input, response, llm_memory)
        except Exception as e:
            print(f"[LOOP] MemoryManager.on_turn_end failed: {e}")

    # NEW: Track files created/modified in this turn
    try:
        from core.agent_file_tracker import (
            scan_workspace_for_changes,
            get_tracked_files,
        )

        changes = scan_workspace_for_changes()
        tracked = get_tracked_files()
        if tracked["all"]:
            print(
                f"[FILE TRACKER] Created: {len(tracked['created'])}, Modified: {len(tracked['modified'])}"
            )
            logger.info(f"Files changed: {tracked['all']}")
    except ImportError:
        pass

    logger.info("Turn completed")

    return response


# ── Classifier ────────────────────────────────────────────────────────────────

_CLASSIFIER_SYSTEM = """You are a message classifier.
Classify the user message into exactly one of these two categories:

  task  — The user wants you to DO something with code:
          - search, find, read, write, create, edit, fix code
          - explain how code works
          - implement, add, create, refactor something
          - Note: Questions that START with "what" but ask you to FIND/SHOW code are TASK

  chat  — The user is making conversation or asking QUESTIONS about past work:
          - greeting (hello, hi)
          - thanks
          - asking about YOU (what are you, who are you)
          - asking about PAST work (what did you find/check/examine/do earlier)
          - asking to SUMMARIZE/RECAP what was discussed
          - Note: Questions like "what classes did you find?" or "what did you check?" are CHAT

Reply with a single word: task or chat. Nothing else."""


def _classify(user_input: str) -> str:
    try:
        response = _qwen_llm.invoke(
            [
                SystemMessage(content=_CLASSIFIER_SYSTEM),
                HumanMessage(content=user_input),
            ]
        )
        record_usage("orchestrator.classifier", response)
        result = response.content.strip().lower()
        return result if result in ("task", "chat") else "task"
    except Exception:
        return "task"


# ── Chat reply ────────────────────────────────────────────────────────────────

_CHAT_SYSTEM = """You are Code-M8, an AI coding assistant.

CONTEXT PROVIDED:
- Previous conversation history
- Memory context about what was done in previous turns (files checked, classes examined, etc.)

TASK: Reply to the user's question using the provided context.

IMPORTANT:
- Use the provided conversation history and memory context to answer questions
- If the context mentions files, classes, or functions that were checked, include them in your answer
- Be specific: mention the actual file names, class names, and function names
- If the context contains relevant information, use it to provide accurate answers

If they ask what you do, explain you help developers read and write code."""


def _chat_reply(user_input: str, his: str) -> str:
    try:
        response = _qwen_llm.invoke(
            [
                SystemMessage(content=_CHAT_SYSTEM),
                HumanMessage(content=user_input + his),
            ]
        )
        record_usage("orchestrator.chat_reply", response)
        return response.content.strip()
    except Exception:
        return "I'm here. What do you need help with?"


def _build_planning_context(
    compact_memory: dict,
    fallback_history: list,
    user_request: str = "",
    budget_chars: int = _PLANNING_CONTEXT_BUDGET_CHARS,
    budget_tokens: int = _PLANNING_CONTEXT_BUDGET_TOKENS,
) -> str:
    """
    Build budgeted planning context using rolling summary + recent turns.

    Enhanced with semantic memory retrieval.
    """
    print("\n" + "=" * 80)
    print("[CONTEXT DEBUG] ══ _build_planning_context() START ══")
    print(f"  Budget: {budget_chars} chars / {budget_tokens} tokens")
    print(f"  compact_memory keys: {list(compact_memory.keys())}")

    # NEW: Get enhanced memory if available
    memory_context = ""
    if ENHANCED_MEMORY and user_request:
        print(f"\n[CONTEXT DEBUG] === ENHANCED MEMORY RETRIEVAL ===")
        try:
            memory_context = build_memory_context_for_orchestrator(user_request)
            if memory_context:
                print(f"  [+] Enhanced memory retrieved:")
                print(f"      {memory_context[:200]}...")
            else:
                print(f"  [+] No enhanced memory found")
        except Exception as e:
            print(f"  [!] Enhanced memory error: {e}")
        print("[CONTEXT DEBUG] === END ENHANCED MEMORY ===\n")

    files = compact_memory.get("files_mentioned", [])
    rolling = compact_memory.get("rolling_summary", "")
    recent_turns = compact_memory.get("recent_turns", [])

    print(f"  compact_memory stats:")
    print(
        f"    - files_mentioned: {len(files)} files -> {files[:10]}{'...' if len(files) > 10 else ''}"
    )
    print(
        f"    - rolling_summary: {len(rolling)} chars, ~{estimate_tokens(rolling)} tokens"
    )
    print(f"    - recent_turns: {len(recent_turns)} turns")
    for rt in recent_turns:
        print(
            f"      • Turn {rt.get('turn_id', '???')}: user='{rt.get('user_message', '')[:40]}...', summary_len={len(rt.get('summary', ''))}"
        )

    print(f"\n[CONTEXT DEBUG] Building context lines:")
    lines = []
    if files:
        lines.append(f"Recent files worked on: {', '.join(files[:20])}")
        print(f"  [+] Files line: {len(lines[-1])} chars")
    if rolling:
        lines.append("Long-term memory summary:")
        lines.append(rolling)
        print(
            f"  [+] Rolling summary: {len(rolling)} chars, {estimate_tokens(rolling)} tokens"
        )
    if recent_turns:
        lines.append("Recent turns:")
        formatted_turns = [_format_turn(t) for t in recent_turns]
        lines.extend(formatted_turns)
        print(
            f"  [+] Recent turns: {len(recent_turns)} turns, {sum(len(t) for t in formatted_turns)} chars"
        )
    elif fallback_history:
        lines.append("Recent turns:")
        lines.extend(_format_turn(t) for t in fallback_history)
        print(f"  [+] Fallback history: {len(fallback_history)} turns")

    context = "\n".join(lines).strip()
    context_chars = len(context)
    context_tokens = estimate_tokens(context)

    print(f"\n[CONTEXT DEBUG] Context before budget check:")
    print(f"  - Total chars: {context_chars}")
    print(f"  - Est tokens: {context_tokens}")
    print(f"  - Budget: {budget_chars} chars / {budget_tokens} tokens")

    was_truncated = False
    if context_tokens > budget_tokens:
        approx_chars = max(1200, budget_tokens * 4)
        context = context[:approx_chars] + "\n...[memory compacted by token budget]"
        was_truncated = True
        print(
            f"  [!] TRUNCATED by token budget: {context_tokens} -> ~{budget_tokens} tokens"
        )
    if len(context) > budget_chars:
        original_len = len(context)
        context = context[: budget_chars - 24] + "\n...[memory compacted]"
        was_truncated = True
        print(f"  [!] TRUNCATED by char budget: {original_len} -> {budget_chars} chars")

    if not was_truncated:
        print(f"  [✓] Context fits within budget, no truncation needed")

    final_tokens = estimate_tokens(context)
    print(f"\n[CONTEXT DEBUG] ══ _build_planning_context() COMPLETE ══")
    print(f"  Final context: {len(context)} chars / {final_tokens} tokens")
    print(f"  Files included: {len(files)}")
    print(
        f"  Recent turns included: {len(recent_turns) if recent_turns else len(fallback_history) if fallback_history else 0}"
    )
    print("=" * 80 + "\n")

    return context
