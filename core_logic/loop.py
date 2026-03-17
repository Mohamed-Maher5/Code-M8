# # """
# # loop.py
# # =======
# # Main turn engine — loads workspace, builds plan, streams response.

# # Each turn:
# #     1. Load workspace files
# #     2. orchestrator.plan()         → Plan
# #     3. dispatcher.run_plan()       → List[TaskResult]
# #     4. orchestrator.summarize()    → final answer
# #     5. Print final answer
# # """

# # from __future__ import annotations

# # import sys
# # from typing import TYPE_CHECKING, List, Optional

# # from core import config
# # from core_logic.dispatcher import Dispatcher
# # from core.types import TaskResult

# # if TYPE_CHECKING:
# #     from core_logic.dispatcher import OrchestratorAgent


# # class Loop:
# #     """
# #     Main conversation loop.
# #     Created once in main.py and started with loop.run().
# #     """

# #     def __init__(
# #         self,
# #         orchestrator: OrchestratorAgent,
# #         dispatcher:   Dispatcher,
# #     ) -> None:
# #         self.orchestrator     = orchestrator
# #         self.dispatcher       = dispatcher
# #         self.session_history: List[str] = []
# #         self.last_plan        = None
# #         self.turn_count       = 0

# #     # ── Entry point ───────────────────────────────────────────────────────────

# #     def run(self) -> None:
# #         """Start the loop. Runs forever until /exit or Ctrl+C."""
# #         self._print_welcome()

# #         while True:
# #             try:
# #                 user_input = self._get_input()

# #                 if user_input is None:
# #                     continue

# #                 if self._handle_command(user_input):
# #                     continue

# #                 self.run_turn(user_input)

# #             except KeyboardInterrupt:
# #                 print("\n\nBye!")
# #                 sys.exit(0)

# #             except Exception as e:
# #                 print(f"\n[ERROR] {e}\n")

# #     # ── Main turn engine ──────────────────────────────────────────────────────

# #     def run_turn(self, user_input: str) -> str:
# #         """
# #         Main turn engine — loads workspace, builds plan, streams response.

# #         Returns the final answer string.
# #         """
# #         self.turn_count += 1

# #         # Step 1 — load workspace files
# #         print(f"\nLoading workspace...")
# #         file_index = self._load_workspace()
# #         print(f"Loaded {len(file_index)} files from {config.WORKSPACE_PATH}")

# #         # Step 2 — build plan using Orchestrator
# #         print(f"Planning...")
# #         try:
# #             plan = self.orchestrator.plan(
# #                 user_request    = user_input,
# #                 session_history = self._build_history_with_files(file_index),
# #             )
# #             self.last_plan = plan
# #         except Exception as e:
# #             print(f"[PLAN ERROR] {e}")
# #             return ""

# #         self._print_plan(plan)

# #         # Step 3 — dispatch all steps in the plan
# #         all_results: List[TaskResult] = []
# #         try:
# #             all_results = self.dispatcher.run_plan(
# #                 plan         = plan,
# #                 orchestrator = self.orchestrator,
# #                 user_request = user_input,
# #             )
# #         except Exception as e:
# #             print(f"[DISPATCH ERROR] {e}")
# #             return ""

# #         # Step 4 — stream response
# #         print(f"\nthinking...\n")
# #         tests_passed = self._tests_passed(all_results)

# #         try:
# #             response = self.orchestrator.summarize(
# #                 user_request = user_input,
# #                 all_results  = all_results,
# #                 tests_passed = tests_passed,
# #             )
# #         except Exception as e:
# #             response = self._fallback_summary(all_results)

# #         # Step 5 — print and save
# #         print(f"{'=' * 50}")
# #         print(response)
# #         print(f"{'=' * 50}\n")

# #         self.session_history.append(f"User: {user_input}")
# #         self.session_history.append(f"Assistant: {response[:300]}")
# #         if len(self.session_history) > 20:
# #             self.session_history = self.session_history[-20:]

# #         return response

# #     # ── Workspace loader ──────────────────────────────────────────────────────

# #     def _load_workspace(self) -> dict:
# #         """
# #         Load all files from the workspace into a dict.
# #         Returns {relative_path: content}.

# #         When context/file_loader.py is built, replace body with:
# #             from context.file_loader import load_files
# #             return load_files(config.WORKSPACE_PATH)
# #         """
# #         from pathlib import Path

# #         file_index = {}
# #         workspace  = Path(config.WORKSPACE_PATH)

# #         if not workspace.exists():
# #             return file_index

# #         for filepath in workspace.rglob("*"):
# #             parts = filepath.relative_to(workspace).parts
# #             if any(p in config.IGNORED_DIRS for p in parts):
# #                 continue
# #             if filepath.suffix in config.IGNORED_EXTENSIONS:
# #                 continue
# #             if not filepath.is_file():
# #                 continue
# #             if filepath.stat().st_size / 1024 > config.MAX_FILE_SIZE_KB:
# #                 continue
# #             try:
# #                 rel = str(filepath.relative_to(workspace))
# #                 file_index[rel] = filepath.read_text(errors="replace")
# #             except Exception:
# #                 continue

# #         return file_index

# #     def _build_history_with_files(self, file_index: dict) -> List[str]:
# #         """
# #         Builds the session history list passed to orchestrator.plan().
# #         Injects the workspace file tree so the model knows what exists.
# #         """
# #         history = []

# #         if file_index:
# #             tree = "\n".join(f"  {path}" for path in sorted(file_index.keys()))
# #             history.append(f"Workspace files:\n{tree}")

# #         history.extend(self.session_history[-10:])
# #         return history

# #     # ── Slash commands ────────────────────────────────────────────────────────

# #     def _handle_command(self, text: str) -> bool:
# #         """Handle slash commands. Returns True if a command was handled."""
# #         cmd = text.strip().lower()

# #         if cmd in ("/exit", "/quit", "exit", "quit"):
# #             print("Bye!")
# #             sys.exit(0)

# #         if cmd == "/clear":
# #             self.session_history.clear()
# #             self.turn_count = 0
# #             print("Session cleared.\n")
# #             return True

# #         if cmd == "/plan":
# #             if self.last_plan:
# #                 self._print_plan(self.last_plan)
# #             else:
# #                 print("No plan yet.\n")
# #             return True

# #         if cmd == "/files":
# #             files = self._load_workspace()
# #             if files:
# #                 for path in sorted(files.keys()):
# #                     print(f"  {path}")
# #             else:
# #                 print("Workspace is empty.\n")
# #             return True

# #         if cmd == "/history":
# #             if self.session_history:
# #                 print("\n".join(self.session_history[-10:]))
# #             else:
# #                 print("No history yet.\n")
# #             return True

# #         if cmd in ("/help", "/?"):
# #             print(
# #                 "\nCommands:\n"
# #                 "  /clear    — clear session history\n"
# #                 "  /plan     — show last plan\n"
# #                 "  /files    — list workspace files\n"
# #                 "  /history  — show recent turns\n"
# #                 "  /exit     — quit\n"
# #             )
# #             return True

# #         return False

# #     # ── Helpers ───────────────────────────────────────────────────────────────

# #     def _get_input(self) -> Optional[str]:
# #         try:
# #             text = input("You: ").strip()
# #             return text if text else None
# #         except EOFError:
# #             sys.exit(0)

# #     def _print_welcome(self) -> None:
# #         print("\n" + "=" * 50)
# #         print("  Code-M8")
# #         print("  /help for commands  |  Ctrl+C to exit")
# #         print("=" * 50 + "\n")

# #     def _print_plan(self, plan) -> None:
# #         steps = plan["steps"]
# #         print(f"Plan ({len(steps)} step{'s' if len(steps) > 1 else ''}):")
# #         for i, step in enumerate(steps, 1):
# #             agent = step["agent"].upper()
# #             instr = step["instruction"][:70]
# #             dots  = "..." if len(step["instruction"]) > 70 else ""
# #             print(f"  {i}. [{agent}] {instr}{dots}")
# #         print()

# #     def _tests_passed(self, results: List[TaskResult]) -> bool:
# #         for result in results:
# #             if result["task"]["agent"] == "runner":
# #                 return result["success"]
# #         return True

# #     def _fallback_summary(self, results: List[TaskResult]) -> str:
# #         parts = []
# #         for result in results:
# #             agent  = result["task"]["agent"].upper()
# #             output = result["output"][:500]
# #             parts.append(f"[{agent}]\n{output}")
# #         return "\n\n".join(parts) if parts else "Done."

















# # # core_logic/loop.py
# # # Main turn engine — loads workspace, runs agents, streams response

# # from context.file_loader import load_files
# # from core.config import WORKSPACE_PATH, OPENROUTER_API_KEY, OPENROUTER_BASE_URL
# # from core.config import HUNTER_MODEL, MINIMAX_MODEL
# # from utils.logger import logger

# # from langchain_openai import ChatOpenAI
# # from agents.orchestrator import Orchestrator
# # from agents.explorer import Explorer
# # from agents.coder import Coder
# # from core_logic.dispatcher import Dispatcher

# # # ── Build LLM clients once at module load ─────────────────────────────────────
# # hunter_llm = ChatOpenAI(
# #     api_key  = OPENROUTER_API_KEY,
# #     base_url = OPENROUTER_BASE_URL,
# #     model    = HUNTER_MODEL,
# #     streaming = True,
# # )

# # minimax_llm = ChatOpenAI(
# #     api_key  = OPENROUTER_API_KEY,
# #     base_url = OPENROUTER_BASE_URL,
# #     model    = MINIMAX_MODEL,
# #     streaming = True,
# # )

# # # ── Build agents once at module load ──────────────────────────────────────────
# # orchestrator = Orchestrator(llm=hunter_llm)
# # explorer     = Explorer(llm=hunter_llm)
# # coder        = Coder(llm=hunter_llm)
# # dispatcher   = Dispatcher(
# #     orchestrator = orchestrator,
# #     explorer     = explorer,
# #     coder        = coder,
# #     test_runner  = None,   # not built yet — dispatcher skips it cleanly
# # )

# # # ── Session history — persists across turns ───────────────────────────────────
# # session_history = []


# # def run_turn(user_input: str) -> str:
# #     """
# #     Called by terminal_ui.py for every user message.
# #     Receives user text → returns response string.
# #     UI renders whatever this returns.
# #     """
# #     logger.info(f"Turn started: {user_input}")

# #     # Step 1 — load workspace files
# #     file_index = load_files(WORKSPACE_PATH)
# #     logger.info(f"Loaded {len(file_index)} files from workspace")

# #     # Step 2 — inject file tree into session history for planner context
# #     history_with_files = []
# #     if file_index:
# #         tree = "\n".join(f"  {path}" for path in sorted(file_index.keys()))
# #         history_with_files.append(f"Workspace files:\n{tree}")
# #     history_with_files.extend(session_history[-10:])

# #     # Step 3 — Orchestrator builds the plan
# #     print("\nplanning...\n")
# #     try:
# #         plan = orchestrator.plan(
# #             user_request    = user_input,
# #             session_history = history_with_files,
# #         )
# #     except Exception as e:
# #         logger.error(f"Plan error: {e}")
# #         return f"Planning failed: {e}"

# #     # Show plan steps in terminal
# #     print(f"Plan ({len(plan['steps'])} steps):")
# #     for i, step in enumerate(plan["steps"], 1):
# #         print(f"  {i}. [{step['agent'].upper()}] {step['instruction'][:70]}")
# #     print()

# #     # Step 4 — Dispatcher runs every step
# #     print("thinking...\n")
# #     try:
# #         all_results = dispatcher.run_plan(
# #             plan         = plan,
# #             orchestrator = orchestrator,
# #             user_request = user_input,
# #         )
# #     except Exception as e:
# #         logger.error(f"Dispatch error: {e}")
# #         return f"Agent error: {e}"

# #     # Step 5 — Orchestrator writes the final answer
# #     try:
# #         response = orchestrator.summarize(
# #             user_request = user_input,
# #             all_results  = all_results,
# #             tests_passed = True,
# #         )
# #     except Exception as e:
# #         # Fallback — stitch raw outputs together
# #         response = "\n\n".join(r["output"] for r in all_results)

# #     # Save to session history
# #     session_history.append(f"User: {user_input}")
# #     session_history.append(f"Assistant: {response[:300]}")
# #     if len(session_history) > 20:
# #         session_history[:] = session_history[-20:]

# #     logger.info("Turn completed")
# #     return response



















# """
# loop.py
# =======
# Main turn engine — loads workspace, runs agents, returns response to UI.

# Each turn:
#     1. Load workspace files
#     2. orchestrator.plan()           → Plan
#     3. dispatcher.run_plan()         → List[TaskResult]  (no runner)
#     4. synthesizer.synthesize()      → final answer string
#     5. Return string to terminal_ui
# """

# from context.file_loader import load_files
# from core.config import (
#     WORKSPACE_PATH,
#     OPENROUTER_API_KEY,
#     OPENROUTER_BASE_URL,
#     HUNTER_MODEL,
#     MINIMAX_MODEL,
# )
# from utils.logger import logger

# from langchain_openai import ChatOpenAI
# from agents.orchestrator import Orchestrator
# from agents.explorer import Explorer
# from agents.coder import Coder
# from core_logic.dispatcher import Dispatcher
# from core_logic.synthesizer import Synthesizer

# # ── LLM clients — built once at module load ───────────────────────────────────
# _hunter_llm = ChatOpenAI(
#     api_key   = OPENROUTER_API_KEY,
#     base_url  = OPENROUTER_BASE_URL,
#     model     = HUNTER_MODEL,
#     streaming = True,
# )

# _minimax_llm = ChatOpenAI(
#     api_key   = OPENROUTER_API_KEY,
#     base_url  = OPENROUTER_BASE_URL,
#     model     = MINIMAX_MODEL,
#     streaming = True,
# )

# # ── Agents — built once at module load ────────────────────────────────────────
# _orchestrator = Orchestrator(llm=_hunter_llm)
# _explorer     = Explorer(llm=_hunter_llm)
# _coder        = Coder(llm=_hunter_llm)

# # Runner excluded for now — dispatcher handles None cleanly
# _dispatcher   = Dispatcher(
#     orchestrator = _orchestrator,
#     explorer     = _explorer,
#     coder        = _coder,
#     test_runner  = None,
# )

# _synthesizer  = Synthesizer(orchestrator=_orchestrator)

# # ── Session history — persists across turns ───────────────────────────────────
# _session_history = []


# def run_turn(user_input: str) -> str:
#     """
#     Called by terminal_ui.py for every user message.
#     Returns the final answer string — UI renders it.
#     """
#     logger.info(f"Turn started: {user_input}")

#     # Step 1 — load workspace files
#     file_index = load_files(WORKSPACE_PATH)
#     logger.info(f"Loaded {len(file_index)} files from workspace")

#     # Step 2 — build plan context with file tree
#     history_with_files = _build_context(file_index)

#     # Step 3 — Orchestrator plans
#     try:
#         plan = _orchestrator.plan(
#             user_request    = user_input,
#             session_history = history_with_files,
#         )
#     except Exception as e:
#         logger.error(f"Plan error: {e}")
#         return f"Could not build a plan: {e}"

#     # Log plan for visibility
#     logger.info(f"Plan: {[s['agent'] for s in plan['steps']]}")

#     # Step 4 — Dispatcher runs every step (runner skipped — it is None)
#     try:
#         all_results = _dispatcher.run_plan(
#             plan         = plan,
#             orchestrator = _orchestrator,
#             user_request = user_input,
#         )
#     except Exception as e:
#         logger.error(f"Dispatch error: {e}")
#         return f"Agent error: {e}"

#     # Step 5 — Synthesizer collects results → final answer
#     response = _synthesizer.synthesize(
#         user_request = user_input,
#         all_results  = all_results,
#     )

#     # Save to session history
#     _session_history.append(f"User: {user_input}")
#     _session_history.append(f"Assistant: {response[:300]}")
#     if len(_session_history) > 20:
#         _session_history[:] = _session_history[-20:]

#     logger.info("Turn completed")
#     return response


# def _build_context(file_index: dict) -> list:
#     """
#     Builds session history list for orchestrator.plan().
#     Injects workspace file tree as first entry.
#     """
#     context = []

#     if file_index:
#         tree = "\n".join(f"  {path}" for path in sorted(file_index.keys()))
#         context.append(f"Workspace files:\n{tree}")

#     context.extend(_session_history[-10:])
#     return context










"""
loop.py
=======
Main turn engine — loads workspace, runs agents, returns response to UI.

Each turn:
    1. Load workspace files
    2. orchestrator.plan()           → Plan
    3. dispatcher.run_plan()         → List[TaskResult]  (no runner)
    4. synthesizer.synthesize()      → final answer string
    5. Return string to terminal_ui
"""

from context.file_loader import load_files
from core.config import (
    WORKSPACE_PATH,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    HUNTER_MODEL,
    MINIMAX_MODEL,
)
from utils.logger import logger

from langchain_openai import ChatOpenAI
from agents.orchestrator import Orchestrator
from agents.explorer import Explorer
from agents.coder import Coder
from core_logic.dispatcher import Dispatcher
from core_logic.synthesizer import Synthesizer
from core.agent_status import set_agent

# ── LLM clients — built once at module load ───────────────────────────────────
_hunter_llm = ChatOpenAI(
    api_key   = OPENROUTER_API_KEY,
    base_url  = OPENROUTER_BASE_URL,
    model     = HUNTER_MODEL,
    streaming = True,
)

_minimax_llm = ChatOpenAI(
    api_key   = OPENROUTER_API_KEY,
    base_url  = OPENROUTER_BASE_URL,
    model     = MINIMAX_MODEL,
    streaming = True,
)

# ── Agents — built once at module load ────────────────────────────────────────
_orchestrator = Orchestrator(llm=_hunter_llm)
_explorer     = Explorer(llm=_hunter_llm)
_coder        = Coder(llm=_minimax_llm)

# Runner excluded for now — dispatcher handles None cleanly
_dispatcher   = Dispatcher(
    orchestrator = _orchestrator,
    explorer     = _explorer,
    coder        = _coder,
    test_runner  = None,
)

_synthesizer  = Synthesizer(orchestrator=_orchestrator)

# ── Session history — persists across turns ───────────────────────────────────
_session_history = []


def run_turn(user_input: str) -> str:
    """
    Called by terminal_ui.py for every user message.
    Returns the final answer string — UI renders it.
    """
    logger.info(f"Turn started: {user_input}")

    # Step 0 — classify: is this a code task or general conversation?
    message_type = _classify(user_input)
    logger.info(f"Message type: {message_type}")

    if message_type == "chat":
        return _chat_reply(user_input)

    # Step 1 — load workspace files
    file_index = load_files(WORKSPACE_PATH)
    logger.info(f"Loaded {len(file_index)} files from workspace")

    # Step 2 — build plan context with file tree
    history_with_files = _build_context(file_index)

    # Step 3 — Orchestrator plans
    set_agent("orchestrator", "planning")
    try:
        plan = _orchestrator.plan(
            user_request    = user_input,
            session_history = history_with_files,
        )
    except Exception as e:
        logger.error(f"Plan error: {e}")
        return f"Could not build a plan: {e}"

    # Log plan for visibility
    logger.info(f"Plan: {[s['agent'] for s in plan['steps']]}")

    # Step 4 — Dispatcher runs every step (runner skipped — it is None)
    set_agent("explorer", "reading workspace")
    try:
        all_results = _dispatcher.run_plan(
            plan         = plan,
            orchestrator = _orchestrator,
            user_request = user_input,
        )
    except Exception as e:
        logger.error(f"Dispatch error: {e}")
        return f"Agent error: {e}"

    # Step 5 — Synthesizer collects results → final answer
    set_agent("orchestrator", "summarising")
    response = _synthesizer.synthesize(
        user_request = user_input,
        all_results  = all_results,
    )

    # Save to session history
    _session_history.append(f"User: {user_input}")
    _session_history.append(f"Assistant: {response[:300]}")
    if len(_session_history) > 20:
        _session_history[:] = _session_history[-20:]

    logger.info("Turn completed")
    return response


def _build_context(file_index: dict) -> list:
    """
    Builds session history list for orchestrator.plan().
    Injects workspace file tree as first entry.
    """
    context = []

    if file_index:
        tree = "\n".join(f"  {path}" for path in sorted(file_index.keys()))
        context.append(f"Workspace files:\n{tree}")

    context.extend(_session_history[-10:])
    return context


# ══════════════════════════════════════════════════════════════════════════════
# MESSAGE CLASSIFIER
# Uses Hunter Alpha to decide: code task or general conversation?
# One small fast call — no agents, no workspace loading.
# ══════════════════════════════════════════════════════════════════════════════

from langchain_core.messages import SystemMessage, HumanMessage

_CLASSIFIER_SYSTEM = """You are a message classifier.
Classify the user message into exactly one of these two categories:

  task  — the user wants to do something with code:
          write, read, explain, fix, add, create, edit, search,
          understand, refactor, debug, implement, find, list files, etc.

  chat  — the user is making conversation, greeting, asking about you,
          saying thanks, or anything NOT related to code or files.

Reply with a single word: task or chat. Nothing else."""


def _classify(user_input: str) -> str:
    """
    Returns "task" or "chat".
    Falls back to "task" on any error so agents always run if unsure.
    """
    try:
        response = _hunter_llm.invoke([
            SystemMessage(content=_CLASSIFIER_SYSTEM),
            HumanMessage(content=user_input),
        ])
        result = response.content.strip().lower()
        return result if result in ("task", "chat") else "task"
    except Exception:
        return "task"   # safe fallback — always run agents if classifier fails


_CHAT_SYSTEM = """You are Code-M8, an AI coding assistant.
The user is making conversation — not asking about code.
Reply naturally and briefly. Keep it under 2 sentences.
If they ask what you do, explain you help developers read and write code."""


def _chat_reply(user_input: str) -> str:
    """
    Generates a natural conversational reply using Hunter Alpha.
    No agents, no workspace, no tools — just a direct LLM response.
    """
    try:
        response = _hunter_llm.invoke([
            SystemMessage(content=_CHAT_SYSTEM),
            HumanMessage(content=user_input),
        ])
        return response.content.strip()
    except Exception as e:
        return "I'm here. What do you need help with?"