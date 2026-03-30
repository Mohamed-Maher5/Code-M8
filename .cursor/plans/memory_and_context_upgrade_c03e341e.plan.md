---
name: Memory and Context Upgrade
overview: Implement a Phase 1 JSON-based memory upgrade that improves long-session recall quality and adds robust context-window compaction without refactoring core architecture.
todos:
  - id: extend-session-schema
    content: Extend session memory records and add rolling summary helpers in core/session_manager.py
    status: completed
  - id: budgeted-planner-context
    content: Implement budgeted planning context assembly in core_logic/loop.py
    status: completed
  - id: agent-message-compaction
    content: Add pre-invoke message compaction in agents/base_agent.py
    status: completed
  - id: retrieval-compaction
    content: Improve context budget handling and dedup in context/graph_search.py
    status: completed
  - id: reset-and-validation
    content: Make /reset truly reset memory state and validate long-session behavior
    status: completed
isProject: false
---

# Phase 1: JSON Memory + Context Compaction

## Goals

- Improve reliability when context fills up.
- Preserve important session knowledge over long chats.
- Keep current architecture and agent flow intact.

## Current Baseline

- Turn persistence exists in `[/home/nour/Downloads/myfinal/Code-M8/core/session_manager.py](/home/nour/Downloads/myfinal/Code-M8/core/session_manager.py)`, but history loaded into planning is very short and aggressively truncated.
- Planning context is assembled in `[/home/nour/Downloads/myfinal/Code-M8/core_logic/loop.py](/home/nour/Downloads/myfinal/Code-M8/core_logic/loop.py)`.
- Agent prompts/messages are built in `[/home/nour/Downloads/myfinal/Code-M8/agents/base_agent.py](/home/nour/Downloads/myfinal/Code-M8/agents/base_agent.py)` with no centralized token-aware compaction before model calls.
- Graph retrieval and compaction are mostly char-based in `[/home/nour/Downloads/myfinal/Code-M8/context/graph_search.py](/home/nour/Downloads/myfinal/Code-M8/context/graph_search.py)`.

## Implementation Plan

- Add a compact memory model in session files:
  - Extend saved turn records in `[/home/nour/Downloads/myfinal/Code-M8/core/session_manager.py](/home/nour/Downloads/myfinal/Code-M8/core/session_manager.py)` with derived fields such as `intent`, `decisions`, `open_threads`, and `artifacts`.
  - Add/update helpers to produce:
    - `recent_turns_context` (short raw tail)
    - `rolling_session_summary` (compressed long-term memory)
  - Keep backward compatibility for existing session JSON files.
- Introduce budgeted context assembly for planning:
  - In `[/home/nour/Downloads/myfinal/Code-M8/core_logic/loop.py](/home/nour/Downloads/myfinal/Code-M8/core_logic/loop.py)`, replace fixed `last_n=3` style prompt input with a budgeted blend:
    - rolling summary
    - recent high-signal turns
    - files touched context
  - Enforce a max context budget before sending to `orchestrator.plan()`.
- Add message compaction before every LLM invoke:
  - In `[/home/nour/Downloads/myfinal/Code-M8/agents/base_agent.py](/home/nour/Downloads/myfinal/Code-M8/agents/base_agent.py)`, add a small compaction utility that preserves:
    - system prompt
    - latest user instruction
    - latest tool result
  - Compress older low-value tool chatter when nearing budget.
  - Keep behavior deterministic and non-destructive.
- Improve retrieval compaction quality:
  - In `[/home/nour/Downloads/myfinal/Code-M8/context/graph_search.py](/home/nour/Downloads/myfinal/Code-M8/context/graph_search.py)`, switch from pure char-limit assembly to budget-aware ordering/dedup for returned snippets.
  - Prioritize top-similarity chunks first, append related context only while budget remains.
- Session UX and observability improvements:
  - Make `/reset` actually reset active session memory state in `[/home/nour/Downloads/myfinal/Code-M8/ui/terminal_ui.py](/home/nour/Downloads/myfinal/Code-M8/ui/terminal_ui.py)` + handler path in `[/home/nour/Downloads/myfinal/Code-M8/ui/input_handler.py](/home/nour/Downloads/myfinal/Code-M8/ui/input_handler.py)`.
  - Add lightweight logs/metrics for context size, compaction triggers, and memory source mix for debugging.

## Validation

- Unit-level checks for session read/write compatibility and compaction behavior.
- Simulated long conversation test to confirm:
  - no prompt blowups,
  - stable recall of prior decisions,
  - no major regression in response quality.
- Manual CLI validation for `/reset` and normal turn flow.

## Out of Scope for Phase 1

- Full graph-backed conversation memory.
- Cross-session semantic search over all historical conversations.

