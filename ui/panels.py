# Rich layout panels — chat, file tree, agent status

from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.console import Console
from rich.align import Align
from rich.table import Table

console = Console()

LOGO_LINES = [
    (" ██████╗ ", "bold red",     "██████╗ ", "bold yellow",  "██████╗ ", "bold green",  "███████╗", "bold cyan"),
    ("██╔════╝ ", "bold red",     "██╔═══██╗", "bold yellow", "██╔══██╗", "bold green",  "██╔════╝", "bold cyan"),
    ("██║      ", "bold red",     "██║   ██║", "bold yellow", "██║  ██║", "bold green",  "█████╗  ", "bold cyan"),
    ("██║      ", "bold red",     "██║   ██║", "bold yellow", "██║  ██║", "bold green",  "██╔══╝  ", "bold cyan"),
    ("╚██████╗ ", "bold red",     "╚██████╔╝", "bold yellow", "██████╔╝", "bold green",  "███████╗", "bold cyan"),
    (" ╚═════╝ ", "bold red",     " ╚═════╝ ", "bold yellow", "╚═════╝ ", "bold green",  "╚══════╝", "bold cyan"),
]

M8_LINES = [
    ("███╗   ███╗", "bold magenta", " █████╗ ", "bold bright_magenta"),
    ("████╗ ████║", "bold magenta", "██╔══██╗", "bold bright_magenta"),
    ("██╔████╔██║", "bold magenta", "╚█████╔╝", "bold bright_magenta"),
    ("██║╚██╔╝██║", "bold magenta", "██╔══██╗", "bold bright_magenta"),
    ("██║ ╚═╝ ██║", "bold magenta", "╚█████╔╝", "bold bright_magenta"),
    ("╚═╝     ╚═╝", "bold magenta", " ╚════╝ ", "bold bright_magenta"),
]

TAGLINE = "Your AI coding teammate — reads your code, writes what you need"

COMMANDS = [
    ("/files",   "list workspace files",  "green"),
    ("/reset",   "clear session history", "yellow"),
    ("/session", "show session info",     "blue"),
    ("/help",    "show all commands",     "cyan"),
    ("/exit",    "quit",                  "red"),
]

def print_logo():
    # build colorful logo line by line
    console.print()
    for i, (line, cols) in enumerate(zip(LOGO_LINES, M8_LINES)):
        c1, s1, c2, s2, c3, s3, c4, s4 = line
        m1, ms1, m2, ms2 = cols
        console.print(
            Align.center(
                f"[{s1}]{c1}[/{s1}][{s2}]{c2}[/{s2}][{s3}]{c3}[/{s3}][{s4}]{c4}[/{s4}]"
                f"    [{ms1}]{m1}[/{ms1}][{ms2}]{m2}[/{ms2}]"
            )
        )

    console.print()
    console.print(Align.center(f"[dim italic]{TAGLINE}[/dim italic]"))
    console.print()

    # commands table — fixed width columns for perfect alignment
    table = Table(
        show_header=False,
        box=None,
        padding=(0, 2),
        expand=False,
        min_width=40
    )
    table.add_column(width=12, justify="left")
    table.add_column(width=2,  justify="center")
    table.add_column(width=26, justify="left")

    for cmd, desc, color in COMMANDS:
        table.add_row(
            f"[bold {color}]{cmd}[/bold {color}]",
            "[dim]→[/dim]",
            f"[dim]{desc}[/dim]"
        )

    console.print(
        Align.center(
            Panel(
                Align.center(table),
                title="[bold white] commands [/bold white]",
                border_style="bright_blue",
                padding=(1, 6)
            )
        )
    )

    console.print()
    console.print(
        Align.center("[dim]── type a command or start typing your request ──[/dim]")
    )
    console.print()