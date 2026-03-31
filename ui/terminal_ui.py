# ui/terminal_ui.py
# Fancy animated terminal UI for Code-M8
# ThinkingBar reads agent_status live every 80ms — icon updates automatically
#
# Interrupt Feature:
#   - Press Ctrl+C to interrupt a running turn
#   - The interrupt flag is checked between execution steps in loop.py
#   - Graceful cancellation returns to prompt without closing the system

import itertools
import _thread
import os
import select
import sys
import threading
import time
import termios
import tty
from typing import Callable, Optional

from prompt_toolkit import prompt
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from rich.align import Align
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from core.config import WORKSPACE_PATH
import core.spec_store as spec_store
from core.session_manager import create_session, reset_session, get_session_id
from core.token_usage import build_usage_table, reset_turn_usage
from ui.input_handler import handle_input
from ui.interrupt import is_interrupted, clear_interrupt, InterruptError, set_interrupt
from ui.panels import print_logo
from ui.renderer import render_response
from utils.logger import logger

console = Console()

ACCENT = "bright_cyan"
DIM = "grey50"
SUCCESS = "bright_green"
ERROR = "bright_red"
WARN = "yellow"

AGENT_ICONS = {
    "orchestrator": "🧠",
    "explorer": "🔍",
    "coder": "⚡",
}

THINK_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

INPUT_STYLE = Style.from_dict(
    {
        "prompt": "ansicyan bold",
        "": "ansiwhite",
    }
)

ESC_INTERRUPT = "__ESC__"


def _create_key_bindings():
    kb = KeyBindings()

    @kb.add("escape", eager=True)
    def handler(event):
        try:
            event.app.exit(result=ESC_INTERRUPT)
        except Exception:
            pass

    return kb


class _EscInterruptWatcher:
    """
    Listen for ESC while a turn is running, then set interrupt flag.
    """

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._fd: Optional[int] = None
        self._old_settings = None
        self._enabled = False

    def start(self) -> None:
        try:
            if not sys.stdin.isatty():
                return
            self._stop.clear()
            self._fd = sys.stdin.fileno()
            self._old_settings = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
            self._drain_pending_input()
            self._enabled = True
            self._thread = threading.Thread(target=self._watch, daemon=True)
            self._thread.start()
        except Exception:
            self._enabled = False

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.2)
        if self._enabled and self._fd is not None and self._old_settings is not None:
            try:
                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_settings)
            except Exception:
                pass
        self._enabled = False
        self._fd = None
        self._old_settings = None

    def _drain_pending_input(self) -> None:
        if self._fd is None:
            return
        while True:
            ready, _, _ = select.select([self._fd], [], [], 0)
            if not ready:
                return
            os.read(self._fd, 1)

    def _watch(self) -> None:
        if self._fd is None:
            return
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select([self._fd], [], [], 0.1)
                if not ready:
                    continue
                data = os.read(self._fd, 1)
                if data == b"\x1b":
                    set_interrupt()
                    try:
                        _thread.interrupt_main()
                    except Exception:
                        pass
                    return
            except Exception:
                return


def _drain_stdin_buffer() -> None:
    """
    Drop pending stdin bytes to prevent repeated ghost ESC events.
    """
    try:
        if not sys.stdin.isatty():
            return
        fd = sys.stdin.fileno()
        while True:
            ready, _, _ = select.select([fd], [], [], 0)
            if not ready:
                return
            os.read(fd, 1)
    except Exception:
        pass


# ── Thinking Bar ──────────────────────────────────────────────────────────────


class ThinkingBar:
    def __init__(self, agent: str = "orchestrator", label: str = "thinking"):
        self.agent = agent
        self.label = label
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._frames = itertools.cycle(THINK_FRAMES)
        self._start = 0.0

    def start(self) -> None:
        self.running = True
        self._start = time.time()
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.running = False
        if self._thread:
            self._thread.join(timeout=1)
        print("\r" + " " * 80 + "\r", end="", flush=True)

    def _animate(self) -> None:
        while self.running:
            try:
                from core.agent_status import get_agent

                current_agent, current_action = get_agent()
            except ImportError:
                current_agent = self.agent
                current_action = self.label

            elapsed = time.time() - self._start
            frame = next(self._frames)
            icon = AGENT_ICONS.get(current_agent, "●")

            warning = (
                "  \033[33m(slow — still working...)\033[0m" if elapsed > 60 else ""
            )

            line = (
                f"\r  {icon}  "
                f"\033[96m{current_agent.upper()}\033[0m  "
                f"\033[90m{current_action}\033[0m  "
                f"\033[96m{frame}\033[0m  "
                f"\033[90m{elapsed:.1f}s\033[0m"
                f"{warning}   "
            )
            print(line, end="", flush=True)
            time.sleep(0.08)


# ── Terminal UI ───────────────────────────────────────────────────────────────


class TerminalUI:
    def __init__(self, loop_fn: Callable[[str], str]):
        self.loop_fn = loop_fn
        self.history = InMemoryHistory()
        self.turn = 0
        self._turn_running = False
        self._last_cancel_at = 0.0

    def handle_command(self, action: str) -> None:
        if action == "show_help":
            self._show_help()
        elif action == "exit":
            self._goodbye()
            raise SystemExit
        elif action == "list_files":
            self._show_files()
        elif action == "reset_session":
            new_id = reset_session()
            self.turn = 0
            clear_interrupt()
            console.print(
                f"  [{SUCCESS}]Session reset.[/{SUCCESS}] [{DIM}]id={new_id}[/{DIM}]"
            )
        elif action == "show_session":
            console.print(
                f"  [{DIM}]Session {get_session_id()} · turn {self.turn} · workspace: {WORKSPACE_PATH}[/{DIM}]"
            )
            self._show_session()
        elif action == "graph_clear":
            self._graph_clear()
        elif action == "spec_load":
            self._spec_load()
        elif action == "spec_show":
            self._spec_show()
        elif action == "spec_clear":
            self._spec_clear()
        # Graph indexing is now automatic - no user-facing commands

    def _graph_clear(self) -> None:
        """Clear all data from graph database with confirmation."""
        console.print()
        console.print(
            Panel(
                Align.center(
                    "[bold red]⚠️  WARNING: This will delete ALL indexed data from the graph database.[/bold red]\n\n"
                    "[dim]• All File nodes will be deleted[/dim]\n"
                    "[dim]• All Chunk nodes will be deleted[/dim]\n"
                    "[dim]• All embeddings will be deleted[/dim]\n"
                    "[dim]• Next request will take 30+ seconds (full re-index)[/dim]\n\n"
                    "[bold yellow]Type 'yes' to confirm, or press Enter to cancel:[/bold yellow]"
                ),
                title="[bold red]⚠️  CONFIRM GRAPH CLEAR  ⚠️[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
        )

        try:
            from prompt_toolkit import prompt
            from prompt_toolkit.styles import Style

            confirm = (
                prompt(
                    "> ",
                    style=Style.from_dict({"": "ansired bold"}),
                )
                .strip()
                .lower()
            )

            if confirm == "yes":
                from context.graph_index import clear_graph_index

                msg = clear_graph_index()
                console.print(f"\n  [{SUCCESS}]{msg}[/{SUCCESS}]\n")
            else:
                console.print(f"\n  [{DIM}]Graph clear cancelled.[/{DIM}]\n")
        except EOFError:
            console.print(f"\n  [{DIM}]Graph clear cancelled.[/{DIM}]\n")
        except Exception as e:
            console.print(f"\n  [{ERROR}]Error: {e}[/{ERROR}]\n")

    def start(self) -> None:
        """
        Main UI loop - runs until user exits.

        Handles:
        - User input via _get_input() (ESC or Ctrl+C to cancel)
        - Command routing via handle_input()
        - Interrupt detection after turns complete

        Note: Use ESC or Ctrl+C to interrupt.
        """
        session_id = create_session()

        # ── NEW: initialise SpecStore with the session id ──────────────────
        spec_store.init(session_id)
        # ───────────────────────────────────────────────────────────────────

        print_logo()
        self._divider()

        while True:
            try:
                # Never carry stale interrupt state into idle prompt.
                if is_interrupted():
                    clear_interrupt()
                _drain_stdin_buffer()
                user_input = self._get_input()

                if user_input == ESC_INTERRUPT:
                    clear_interrupt()
                    now = time.time()
                    # Debounce repeated prompt cancellations from buffered keys.
                    if now - self._last_cancel_at > 0.6:
                        console.print(f"\n  [{WARN}]Turn cancelled.[/{WARN}]\n")
                        self._divider()
                    self._last_cancel_at = now
                    continue

                if is_interrupted():
                    clear_interrupt()
                    console.print(f"\n  [{WARN}]Turn cancelled.[/{WARN}]\n")
                    self._divider()
                    continue

                if not user_input:
                    continue

                kind, value = handle_input(user_input)

                if kind == "command":
                    self.handle_command(value)
                else:
                    self._run_turn(value)

            except KeyboardInterrupt:
                if self._turn_running:
                    clear_interrupt()
                    console.print(f"\n  [{WARN}]Turn cancelled.[/{WARN}]\n")
                    self._divider()
                    continue
                self._goodbye()
                break
            except SystemExit:
                break
            except Exception as e:
                logger.error(f"UI error: {e}")
                console.print(f"\n  [{ERROR}]Error:[/{ERROR}] [{DIM}]{e}[/{DIM}]\n")

    # ── Spec commands ─────────────────────────────────────────────────────────

    def _spec_load(self) -> None:
        """Prompt the user for a spec file path and load it."""
        console.print()
        console.print(
            f"  [{ACCENT}]Enter spec file path (relative to workspace), or paste inline text:[/{ACCENT}]"
        )
        try:
            source = prompt("> ", style=INPUT_STYLE).strip()
        except EOFError:
            return

        if not source:
            console.print(f"  [{WARN}]Nothing entered.[/{WARN}]\n")
            return

        console.print(f"  [{DIM}]Parsing spec…[/{DIM}]")

        try:
            import json
            import core.spec_store as spec_store
            from tools.read_spec import read_spec as _read_spec_tool

            raw = _read_spec_tool.invoke({"source": source})
            parsed = json.loads(raw)

            if isinstance(parsed, dict) and "error" in parsed:
                console.print(
                    f"  [{ERROR}]Spec parse error:[/{ERROR}] {parsed['error']}\n"
                )
                return

            spec_store.set_criteria(parsed, source=source)
            console.print(
                f"  [{SUCCESS}]Loaded {len(parsed)} criteria from '{source}'[/{SUCCESS}]\n"
            )
            self._spec_show()
        except Exception as e:
            console.print(f"  [{ERROR}]Failed to load spec:[/{ERROR}] {e}\n")

    def _spec_show(self) -> None:
        """Display the current loaded spec criteria."""
        import core.spec_store as spec_store

        if not spec_store.has_spec():
            console.print(
                f"  [{WARN}]No spec loaded. Use /spec load to load one.[/{WARN}]\n"
            )
            return

        criteria = spec_store.get_criteria()
        console.print()

        table = Table(show_header=True, box=None, padding=(0, 1))
        table.add_column("ID", style="cyan", width=8)
        table.add_column("Priority", style="yellow", width=10)
        table.add_column("Category", style="blue", width=12)
        table.add_column("Testable", style="green", width=9)
        table.add_column("Description")

        for c in criteria:
            table.add_row(
                c["id"],
                c["priority"],
                c["category"],
                "yes" if c.get("testable") else "no",
                c["description"],
            )

        console.print(
            Panel(
                table,
                title=f"[{ACCENT}] loaded spec: {spec_store._spec_source} [/{ACCENT}]",
                border_style=ACCENT,
                padding=(1, 2),
            )
        )
        console.print()

    def _spec_clear(self) -> None:
        """Clear the current spec from memory and disk."""
        import core.spec_store as spec_store

        spec_store.clear()
        console.print(f"  [{WARN}]Spec cleared.[/{WARN}]\n")

    # ── Other commands ────────────────────────────────────────────────────────

    def _show_session(self) -> None:
        import core.spec_store as spec_store

        spec_summary = spec_store.summary_text()
        console.print(
            f"  [{DIM}]Turn {self.turn} · workspace: {WORKSPACE_PATH}[/{DIM}]\n"
            f"  [{DIM}]Spec: {spec_summary}[/{DIM}]"
        )

    # ── Turn ──────────────────────────────────────────────────────────────────

    def _run_turn(self, user_input: str) -> None:
        """
        Execute a single turn: planning → dispatch → synthesize.

        Press Ctrl+C to interrupt. The KeyboardInterrupt is caught
        in the main loop and exits gracefully.

        Args:
            user_input: The user's request/question
        """
        self.turn += 1
        console.print()
        reset_turn_usage()

        bar = ThinkingBar("orchestrator", "planning")
        bar.start()
        watcher = _EscInterruptWatcher()
        watcher.start()
        self._turn_running = True

        try:
            response = self.loop_fn(user_input)
        except InterruptError:
            watcher.stop()
            self._turn_running = False
            bar.stop()
            console.print(f"\n  [{WARN}]Turn cancelled.[/{WARN}]\n")
            self._render_token_usage()
            clear_interrupt()
            self._divider()
            return
        except KeyboardInterrupt:
            watcher.stop()
            self._turn_running = False
            bar.stop()
            console.print(f"\n  [{WARN}]Turn cancelled.[/{WARN}]\n")
            self._render_token_usage()
            clear_interrupt()
            self._divider()
            return
        except Exception as e:
            watcher.stop()
            self._turn_running = False
            bar.stop()
            console.print(f"  [{ERROR}]Error:[/{ERROR}] {e}\n")
            self._render_token_usage()
            return

        watcher.stop()
        self._turn_running = False
        bar.stop()

        # Check interrupt flag (can be set by external code)
        if is_interrupted():
            console.print(f"  [{WARN}]Turn cancelled.[/{WARN}]\n")
            self._render_token_usage()
            clear_interrupt()
            self._divider()
            return

        self._render_response(response)
        self._render_token_usage()
        self._divider()

    def _render_response(self, text: str) -> None:
        console.print()
        if "```" in text:
            render_response(text)
        else:
            console.print(
                Panel(
                    Markdown(text),
                    border_style=ACCENT,
                    padding=(1, 2),
                    title=f"[{DIM}]Code-M8[/{DIM}]",
                    title_align="right",
                )
            )
        console.print()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_input(self) -> str:
        """
        Get user input from the terminal.

        Returns:
            User input string (stripped of whitespace)
            ESC_INTERRUPT if ESC or Ctrl+C pressed
            "/exit" on EOF
        """
        try:
            return prompt(
                FormattedText([("class:prompt", "  ❯ ")]),
                style=INPUT_STYLE,
                history=self.history,
                key_bindings=_create_key_bindings(),
            ).strip()
        except EOFError:
            return "/exit"

    def _divider(self) -> None:
        console.print(f"  [{DIM}]{'─' * 60}[/{DIM}]")

    def _show_help(self) -> None:
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(width=14)
        table.add_column(width=2, justify="center")
        table.add_column()
        for cmd, desc in [
            ("/files", "list workspace files"),
            ("/reset", "clear session history"),
            ("/session", "show session info"),
            ("/spec load", "load a spec file or paste inline text"),
            ("/spec show", "display loaded criteria"),
            ("/spec clear", "remove current spec"),
            ("/graph-clear", "⚠️ wipe graph DB (full re-index next time)"),
            ("/help", "show this help"),
            ("/exit", "quit"),
        ]:
            table.add_row(
                f"[{ACCENT}]{cmd}[/{ACCENT}]",
                f"[{DIM}]→[/{DIM}]",
                f"[{DIM}]{desc}[/{DIM}]",
            )
        console.print()
        console.print(
            Panel(
                Align.center(table),
                title=f"[{ACCENT}] commands [/{ACCENT}]",
                border_style=ACCENT,
                padding=(1, 4),
            )
        )
        console.print()

    def _render_token_usage(self) -> None:
        usage_table = build_usage_table()
        if usage_table is None:
            return
        console.print()
        console.print(
            Panel(
                usage_table,
                border_style=ACCENT,
                padding=(0, 1),
                title=f"[{DIM}]Token Usage[/{DIM}]",
                title_align="right",
            )
        )

    def _show_files(self) -> None:
        from pathlib import Path
        import core.config as CONFIG

        workspace = Path(CONFIG.WORKSPACE_PATH).resolve()

        if not workspace.exists():
            console.print(f"  [{WARN}]Workspace is empty.[/{WARN}]\n")
            return

        console.print()
        for item in sorted(workspace.rglob("*")):
            parts = item.relative_to(workspace).parts
            if any(p in CONFIG.BLOCKED_DIRS for p in parts):
                continue
            if item.is_file():
                rel = item.relative_to(workspace)
                size = round(item.stat().st_size / 1024, 2)
                console.print(
                    f"  [{ACCENT}]📄[/{ACCENT}]  [{DIM}]{rel}[/{DIM}]"
                    f"  [{DIM}]{size}kb[/{DIM}]"
                )
        console.print()

    def _goodbye(self) -> None:
        console.print()
        console.print(Align.center(f"[{ACCENT}]goodbye[/{ACCENT}]"))
        console.print()
