# core_logic/loop.py
# Main turn engine — loads workspace, runs agents, returns response to UI
#
# Each turn:
#     1. Load workspace files
#     2. orchestrator.plan()        → Plan
#     3. dispatcher.run_plan()      → List[TaskResult]  (no runner yet)
#     4. synthesizer.synthesize()   → final answer string
#     5. Return string to terminal_ui

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from agents.coder        import Coder
from agents.explorer     import Explorer
from agents.orchestrator import Orchestrator
from context.file_loader import load_files
from core.config import (
    HUNTER_MODEL,
    MINIMAX_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    WORKSPACE_PATH,
)
from core_logic.dispatcher  import Dispatcher
from core_logic.synthesizer import Synthesizer
from utils.logger import logger


# ── Status helper — silent if agent_status not built yet ──────────────────────

def _set_status(agent: str, action: str) -> None:
    try:
        from core.agent_status import set_agent
        set_agent(agent, action)
    except ImportError:
        pass


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

_dispatcher  = Dispatcher(
    orchestrator = _orchestrator,
    explorer     = _explorer,
    coder        = _coder,
    test_runner  = None,    # not built yet — dispatcher skips it cleanly
)

_synthesizer = Synthesizer(orchestrator=_orchestrator)


# ── Session history — persists across turns ───────────────────────────────────

_session_history = []


# ── Main turn engine ──────────────────────────────────────────────────────────

def run_turn(user_input: str) -> str:
    """
    Called by terminal_ui.py for every user message.
    Returns the final answer string — UI renders it.
    """
    logger.info(f"Turn started: {user_input}")

    # step 0 — classify: code task or general conversation?
    message_type = _classify(user_input)
    logger.info(f"Message type: {message_type}")

    if message_type == "chat":
        return _chat_reply(user_input)

    # step 1 — load workspace files
    file_index = load_files(WORKSPACE_PATH)
    logger.info(f"Loaded {len(file_index)} files from workspace")

    # step 2 — build plan context with file tree
    history_with_files = _build_context(file_index)

    # step 3 — orchestrator plans
    _set_status("orchestrator", "planning")
    try:
        plan = _orchestrator.plan(
            user_request    = user_input,
            session_history = history_with_files,
        )
    except Exception as e:
        logger.error(f"Plan error: {e}")
        return f"Could not build a plan: {e}"

    logger.info(f"Plan: {[s['agent'] for s in plan['steps']]}")

    # step 4 — dispatcher runs every step
    _set_status("explorer", "reading workspace")
    try:
        all_results = _dispatcher.run_plan(
            plan         = plan,
            orchestrator = _orchestrator,
            user_request = user_input,
        )
    except Exception as e:
        logger.error(f"Dispatch error: {e}")
        return f"Agent error: {e}"

    # step 5 — synthesizer collects results → final answer
    _set_status("orchestrator", "summarising")
    response = _synthesizer.synthesize(
        user_request = user_input,
        all_results  = all_results,
    )

    # save to session history
    _session_history.append(f"User: {user_input}")
    _session_history.append(f"Assistant: {response[:300]}")
    if len(_session_history) > 20:
        _session_history[:] = _session_history[-20:]

    logger.info("Turn completed")
    return response


# ── Context builder ───────────────────────────────────────────────────────────

def _build_context(file_index: dict) -> list:
    # builds session history list for orchestrator.plan()
    # injects workspace file tree as first entry
    context = []

    if file_index:
        tree = "\n".join(f"  {path}" for path in sorted(file_index.keys()))
        context.append(f"Workspace files:\n{tree}")

    context.extend(_session_history[-10:])
    return context


# ── Message classifier ────────────────────────────────────────────────────────

_CLASSIFIER_SYSTEM = """You are a message classifier.
Classify the user message into exactly one of these two categories:

  task  — the user wants to do something with code:
          write, read, explain, fix, add, create, edit, search,
          understand, refactor, debug, implement, find, list files, etc.

  chat  — the user is making conversation, greeting, asking about you,
          saying thanks, or anything NOT related to code or files.

Reply with a single word: task or chat. Nothing else."""


def _classify(user_input: str) -> str:
    # returns "task" or "chat"
    # falls back to "task" on any error so agents always run if unsure
    try:
        response = _hunter_llm.invoke([
            SystemMessage(content=_CLASSIFIER_SYSTEM),
            HumanMessage(content=user_input),
        ])
        result = response.content.strip().lower()
        return result if result in ("task", "chat") else "task"
    except Exception:
        return "task"


# ── Chat reply ────────────────────────────────────────────────────────────────

_CHAT_SYSTEM = """You are Code-M8, an AI coding assistant.
The user is making conversation — not asking about code.
Reply naturally and briefly. Keep it under 2 sentences.
If they ask what you do, explain you help developers read and write code."""


def _chat_reply(user_input: str) -> str:
    # direct Hunter response for conversation — no agents, no workspace
    try:
        response = _hunter_llm.invoke([
            SystemMessage(content=_CHAT_SYSTEM),
            HumanMessage(content=user_input),
        ])
        return response.content.strip()
    except Exception:
        return "I'm here. What do you need help with?"