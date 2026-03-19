# ui/terminal_ui.py
# Fancy animated terminal UI for Code-M8
# ThinkingBar reads agent_status live every 80ms — icon updates automatically

import itertools
import threading
import time
from typing import Callable, Optional

from prompt_toolkit import prompt
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style
from rich.align import Align
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from core.config import WORKSPACE_PATH
from core.session_manager import create_session
from ui.input_handler import handle_input
from ui.panels import print_logo
from ui.renderer import render_response
from utils.logger import logger

console = Console()

ACCENT  = "bright_cyan"
DIM     = "grey50"
SUCCESS = "bright_green"
ERROR   = "bright_red"
WARN    = "yellow"

AGENT_ICONS = {
    "orchestrator": "🧠",
    "explorer":     "🔍",
    "coder":        "⚡",
}

THINK_FRAMES = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]

INPUT_STYLE = Style.from_dict({
    "prompt": "ansicyan bold",
    "":       "ansiwhite",
})


# ── Thinking Bar ──────────────────────────────────────────────────────────────

class ThinkingBar:

    def __init__(self, agent: str = "orchestrator", label: str = "thinking"):
        self.agent   = agent
        self.label   = label
        self.running = False
        self._thread : Optional[threading.Thread] = None
        self._frames  = itertools.cycle(THINK_FRAMES)
        self._start   = 0.0

    def start(self) -> None:
        self.running = True
        self._start  = time.time()
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
                current_agent  = self.agent
                current_action = self.label

            elapsed = time.time() - self._start
            frame   = next(self._frames)
            icon    = AGENT_ICONS.get(current_agent, "●")

            warning = (
                "  \033[33m(slow — still working...)\033[0m"
                if elapsed > 60 else ""
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
        self.turn    = 0

    def handle_command(self, action: str) -> None:
        if action == "show_help":
            self._show_help()
        elif action == "exit":
            self._goodbye()
            raise SystemExit
        elif action == "list_files":
            self._show_files()
        elif action == "reset_session":
            console.print(f"  [{WARN}]Session cleared.[/{WARN}]")
        elif action == "show_session":
            console.print(f"  [{DIM}]Turn {self.turn} · workspace: {WORKSPACE_PATH}[/{DIM}]")

    def start(self) -> None:
        create_session()
        print_logo()
        self._divider()

        while True:
            try:
                user_input = self._get_input()
                if not user_input:
                    continue

                kind, value = handle_input(user_input)

                if kind == "command":
                    self.handle_command(value)
                else:
                    self._run_turn(value)

            except KeyboardInterrupt:
                self._goodbye()
                break
            except SystemExit:
                break
            except Exception as e:
                logger.error(f"UI error: {e}")
                console.print(f"\n  [{ERROR}]Error:[/{ERROR}] [{DIM}]{e}[/{DIM}]\n")

    # ── Turn ──────────────────────────────────────────────────────────────────

    def _run_turn(self, user_input: str) -> None:
        self.turn += 1
        console.print()

        bar = ThinkingBar("orchestrator", "planning")
        bar.start()

        try:
            response = self.loop_fn(user_input)
        except Exception as e:
            bar.stop()
            console.print(f"  [{ERROR}]Error:[/{ERROR}] {e}\n")
            return

        bar.stop()
        self._render_response(response)
        self._divider()

    def _render_response(self, text: str) -> None:
        console.print()
        if "```" in text:
            render_response(text)
        else:
            console.print(
                Panel(
                    Markdown(text),
                    border_style = ACCENT,
                    padding      = (1, 2),
                    title        = f"[{DIM}]Code-M8[/{DIM}]",
                    title_align  = "right",
                )
            )
        console.print()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_input(self) -> str:
        try:
            return prompt(
                FormattedText([("class:prompt", "  ❯ ")]),
                style   = INPUT_STYLE,
                history = self.history,
            ).strip()
        except EOFError:
            return "/exit"

    def _divider(self) -> None:
        console.print(f"  [{DIM}]{'─' * 60}[/{DIM}]")

    def _show_help(self) -> None:
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(width=12)
        table.add_column(width=2, justify="center")
        table.add_column()
        for cmd, desc in [
            ("/files",   "list workspace files"),
            ("/reset",   "clear session history"),
            ("/session", "show session info"),
            ("/help",    "show this help"),
            ("/exit",    "quit"),
        ]:
            table.add_row(
                f"[{ACCENT}]{cmd}[/{ACCENT}]",
                f"[{DIM}]→[/{DIM}]",
                f"[{DIM}]{desc}[/{DIM}]",
            )
        console.print()
        console.print(Panel(
            Align.center(table),
            title        = f"[{ACCENT}] commands [/{ACCENT}]",
            border_style = ACCENT,
            padding      = (1, 4),
        ))
        console.print()

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
                rel  = item.relative_to(workspace)
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