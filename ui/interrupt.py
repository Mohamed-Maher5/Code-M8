# ui/interrupt.py
# Thread-safe interrupt flag for graceful cancellation of agent execution
#
# This module provides a mechanism to interrupt running agent turns without
# closing the system. When ESC is pressed, the flag is set, and the running
# turn checks this flag between steps to gracefully stop.
#
# Architecture:
#   - Uses threading.Event for thread-safe flag (works across threads)
#   - Interrupt can be set from:
#     1. prompt_toolkit key binding (when waiting for input)
#     2. Manual call to set_interrupt() (for testing)
#   - Checked in loop.py between agent execution steps
#
# Usage:
#   from ui.interrupt import set_interrupt, is_interrupted, clear_interrupt
#
#   # During agent execution, periodically check:
#   if is_interrupted():
#       raise InterruptError("Turn cancelled by user")
#
#   # After handling interrupt:
#   clear_interrupt()

import threading
from typing import Optional

# Singleton event instance - thread-safe flag that can be set/checked across threads
# The Event starts in "not set" state (is_set() returns False)
_interrupt_event: threading.Event = threading.Event()


# Custom exception for interrupt handling - allows clean separation from KeyboardInterrupt
class InterruptError(Exception):
    """Raised when user presses ESC to cancel the current turn."""

    pass


def set_interrupt() -> None:
    """
    Signal that an interrupt has been requested (ESC pressed).

    This sets the internal Event flag, which will be detected by
    the running turn on its next checkpoint.

    Thread-safe: can be called from any thread while loop.py is executing.
    """
    _interrupt_event.set()


def is_interrupted() -> bool:
    """
    Check if an interrupt has been requested.

    Returns:
        True if ESC was pressed and interrupt is pending
        False if no interrupt has been requested

    Thread-safe: uses threading.Event internally
    """
    return _interrupt_event.is_set()


def clear_interrupt() -> None:
    """
    Clear the interrupt flag after handling.

    Must be called after an interrupt is handled to reset the state
    for the next turn. Failure to clear will cause all subsequent
    turns to be immediately cancelled.
    """
    _interrupt_event.clear()


def wait_for_interrupt(timeout: Optional[float] = None) -> bool:
    """
    Block until interrupt is set or timeout expires.

    Args:
        timeout: Maximum seconds to wait (None = wait forever)

    Returns:
        True if interrupt was set
        False if timeout expired first

    Useful for implementing timeout-based auto-cancellation.
    """
    return _interrupt_event.wait(timeout=timeout)
