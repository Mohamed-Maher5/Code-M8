# core_logic/planner.py
# Owns all plan-related logic — used by loop.py
# Simple and usable — no complexity

from __future__ import annotations

from typing import List

from core.types import Plan, Task, make_task
from utils.logger import logger


def validate_plan(plan: Plan) -> bool:
    steps  = plan["steps"]
    agents = [s["agent"] for s in steps]

    if not agents:
        logger.warning("Planner: empty plan")
        return False

    if "coder" in agents and "explorer" in agents:
        if agents.index("coder") < agents.index("explorer"):
            logger.warning("Planner: coder before explorer — invalid")
            return False

    return True


def plan_summary(plan: Plan) -> str:
    steps  = plan["steps"]
    agents = " → ".join(s["agent"] for s in steps)
    return f"{len(steps)} step{'s' if len(steps) > 1 else ''}: {agents}"


def print_plan(plan: Plan) -> None:
    steps = plan["steps"]
    print(f"\n  📋 Plan — {len(steps)} step{'s' if len(steps) > 1 else ''}:")
    for i, step in enumerate(steps, 1):
        instr = step["instruction"][:70]
        dots  = "..." if len(step["instruction"]) > 70 else ""
        print(f"     {i}. [{step['agent'].upper()}] {instr}{dots}")
    print()


def fallback_plan(user_request: str) -> Plan:
    logger.warning("Planner: using fallback plan")
    return Plan(steps=[
        make_task("explorer", f"Explore the codebase for: {user_request}"),
        make_task("coder",    f"Implement: {user_request}"),
    ])