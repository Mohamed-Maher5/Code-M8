# core_logic/loop.py
# Main turn engine — loads workspace, runs agents, returns response to UI
#
# Each turn:
#     1. orchestrator.plan()        → Plan
#     2. dispatcher.run_plan()      → List[TaskResult]
#     3. synthesizer.synthesize()   → final answer string
#     4. Return string to terminal_ui

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from agents.coder        import Coder
from agents.explorer     import Explorer
from agents.orchestrator import Orchestrator
from core.config import (
    HUNTER_MODEL,
    MINIMAX_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
)
from core_logic.dispatcher  import Dispatcher
from core_logic.synthesizer import Synthesizer
from core_logic.planner     import validate_plan, print_plan, plan_summary, fallback_plan
from utils.logger import logger

from core.session_manager import save_turn, load_history


# ── Status helper ─────────────────────────────────────────────────────────────

def _set_status(agent: str, action: str) -> None:
    try:
        from core.agent_status import set_agent
        set_agent(agent, action)
    except ImportError:
        pass


# ── LLM clients ───────────────────────────────────────────────────────────────

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


# ── Agents ────────────────────────────────────────────────────────────────────

_orchestrator = Orchestrator(llm=_hunter_llm)
_explorer     = Explorer(llm=_hunter_llm)
_coder        = Coder(llm=_hunter_llm)

_dispatcher  = Dispatcher(
    orchestrator = _orchestrator,
    explorer     = _explorer,
    coder        = _coder,
)

_synthesizer = Synthesizer(orchestrator=_orchestrator)


# ── Session history ───────────────────────────────────────────────────────────

_session_history = []


# ── Main turn engine ──────────────────────────────────────────────────────────

def run_turn(user_input: str) -> str:
    logger.info(f"Turn started: {user_input}")
    history=load_history(last_n=5)
   
    # step 0 — classify
    message_type = _classify(user_input)
    logger.info(f"Message type: {message_type}")

    if message_type == "chat":
        return _chat_reply(user_input," ".join(history))

    # step 1 — orchestrator plans using session history only
    _set_status("orchestrator", "planning")
    try:
        plan = _orchestrator.plan(
            user_request    = user_input,
            session_history = history,
        )
    except Exception as e:
        logger.error(f"Plan error: {e}")
        return f"Could not build a plan: {e}"

    # validate and print plan
    if not validate_plan(plan):
        plan = fallback_plan(user_input)

    print_plan(plan)
    logger.info(f"Plan: {plan_summary(plan)}")

    # step 2 — dispatch
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

    # step 3 — synthesize
    _set_status("orchestrator", "summarising")
    response = _synthesizer.synthesize(
        user_request = user_input,
        all_results  = all_results,
    )
    save_turn(
        user_message = user_input,
        all_results  = all_results,
        final_answer = response,
    )

    # save history
    # _session_history.append(f"User: {user_input}")
    # _session_history.append(f"Assistant: {response[:300]}")
    # if len(_session_history) > 20:
    #     _session_history[:] = _session_history[-20:]

    logger.info("Turn completed")
    



    return response


# ── Classifier ────────────────────────────────────────────────────────────────

_CLASSIFIER_SYSTEM = """You are a message classifier.
Classify the user message into exactly one of these two categories:

  task  — the user wants to do something with code:
          write, read, explain, fix, add, create, edit, search,
          understand, refactor, debug, implement, find, list files, etc.

  chat  — the user is making conversation, greeting, asking about you,
          saying thanks, or anything NOT related to code or files.

Reply with a single word: task or chat. Nothing else."""


def _classify(user_input: str) -> str:
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


def _chat_reply(user_input: str,his:str) -> str:
    try:
        response = _hunter_llm.invoke([
            SystemMessage(content=_CHAT_SYSTEM),
            HumanMessage(content=user_input+his),
        ])
        return response.content.strip()
    except Exception:
        return "I'm here. What do you need help with?"