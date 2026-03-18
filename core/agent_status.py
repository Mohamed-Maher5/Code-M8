"""
agent_status.py
===============
Shared status object between loop.py and terminal_ui.py.
loop.py writes which agent is active.
terminal_ui.py reads it to update the spinner icon.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentStatus:
    """Current agent running — shared between loop and UI."""
    agent:  str = "orchestrator"
    action: str = "thinking"


# Singleton — import this everywhere
status = AgentStatus()


def set_agent(agent: str, action: str = "thinking") -> None:
    """Called by loop.py when switching agents."""
    status.agent  = agent
    status.action = action


def get_agent() -> tuple[str, str]:
    """Called by terminal_ui.py to read current agent."""
    return status.agent, status.action