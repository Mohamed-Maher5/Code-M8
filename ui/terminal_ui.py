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
import core.spec_store as spec_store
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
            # console.print(f"  [{DIM}]Turn {self.turn} · workspace: {WORKSPACE_PATH}[/{DIM}]")
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
        console.print(Panel(
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
            padding=(1, 2)
        ))
        
        try:
            from prompt_toolkit import prompt
            from prompt_toolkit.styles import Style
            
            confirm = prompt(
                "> ",
                style=Style.from_dict({"": "ansired bold"}),
            ).strip().lower()
            
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
        session_id = create_session()
 
        # ── NEW: initialise SpecStore with the session id ──────────────────
        spec_store.init(session_id)
        # ───────────────────────────────────────────────────────────────────

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


    # ── Spec commands ─────────────────────────────────────────────────────────
 
    def _spec_load(self) -> None:
        """Prompt the user for a spec file path and load it."""
        console.print()
        console.print(f"  [{ACCENT}]Enter spec file path (relative to workspace), or paste inline text:[/{ACCENT}]")
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
                console.print(f"  [{ERROR}]Spec parse error:[/{ERROR}] {parsed['error']}\n")
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
            console.print(f"  [{WARN}]No spec loaded. Use /spec load to load one.[/{WARN}]\n")
            return
 
        criteria = spec_store.get_criteria()
        console.print()
 
        table = Table(show_header=True, box=None, padding=(0, 1))
        table.add_column("ID",       style="cyan",  width=8)
        table.add_column("Priority", style="yellow", width=10)
        table.add_column("Category", style="blue",   width=12)
        table.add_column("Testable", style="green",  width=9)
        table.add_column("Description")
 
        for c in criteria:
            table.add_row(
                c["id"],
                c["priority"],
                c["category"],
                "yes" if c.get("testable") else "no",
                c["description"],
            )
 
        console.print(Panel(
            table,
            title   = f"[{ACCENT}] loaded spec: {spec_store._spec_source} [/{ACCENT}]",
            border_style = ACCENT,
            padding  = (1, 2),
        ))
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
        table.add_column(width=14)
        table.add_column(width=2, justify="center")
        table.add_column()
        for cmd, desc in [
            ("/files",   "list workspace files"),
            ("/reset",   "clear session history"),
            ("/session", "show session info"),
            ("/spec load",   "load a spec file or paste inline text"),
            ("/spec show",   "display loaded criteria"),
            ("/spec clear",  "remove current spec"),
            ("/graph-clear", "⚠️ wipe graph DB (full re-index next time)"),
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
