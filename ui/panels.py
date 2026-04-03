# ui/panels.py
# Animated logo and robot ASCII art for Code-M8

import asyncio
import time
from rich.panel import Panel
from rich.console import Console
from rich.align import Align
from rich.table import Table
from rich.live import Live
from rich.columns import Columns

console = Console()

TAGLINE = "Your AI coding teammate — reads your code, writes what you need"

COMMANDS = [
    ("/files",   "list workspace files",  "green"),
    ("/reset",   "clear session history", "yellow"),
    ("/session", "show session info",     "blue"),
    ("/help",    "show all commands",     "cyan"),
    ("/exit",    "quit",                  "red"),
]

LOGO = """\
[bold bright_cyan] ██████╗ ██████╗ ██████╗ ███████╗    ███╗   ███╗ █████╗ [/bold bright_cyan]
[bold bright_cyan]██╔════╝██╔═══██╗██╔══██╗██╔════╝    ████╗ ████║██╔══██╗[/bold bright_cyan]
[bold bright_cyan]██║     ██║   ██║██║  ██║█████╗      ██╔████╔██║╚█████╔╝[/bold bright_cyan]
[bold bright_cyan]██║     ██║   ██║██║  ██║██╔══╝      ██║╚██╔╝██║██╔══██╗[/bold bright_cyan]
[bold bright_cyan]╚██████╗╚██████╔╝██████╔╝███████╗    ██║ ╚═╝ ██║╚█████╔╝[/bold bright_cyan]
[bold bright_cyan] ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝    ╚═╝     ╚═╝ ╚════╝ [/bold bright_cyan]"""

ROBOT_OPEN = """\
[bold red]        ●[/bold red]
[bold red]        │[/bold red]
[bold white]  ╔═══════════════╗[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░░░░░░░░░░░░░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]╔═════╗[/bold white][bold bright_cyan]░[/bold bright_cyan][bold white]╔═════╗[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░░░░░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░░░░░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░░░░░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░░░░░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]╚═════╝[/bold white][bold bright_cyan]░[/bold bright_cyan][bold white]╚═════╝[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░░░[/bold bright_cyan][bold white]╰───────╯[/bold white][bold bright_cyan]░░░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░░░░░░░░░░░░░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ╚═══════════════╝[/bold white]"""

ROBOT_BLINK = """\
[bold red]        ●[/bold red]
[bold red]        │[/bold red]
[bold white]  ╔═══════════════╗[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░░░░░░░░░░░░░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]╔═════╗[/bold white][bold bright_cyan]░[/bold bright_cyan][bold white]╔═════╗[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░░─░░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░░─░░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░░░░░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░░░░░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]╚═════╝[/bold white][bold bright_cyan]░[/bold bright_cyan][bold white]╚═════╝[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░░░[/bold bright_cyan][bold white]╰───────╯[/bold white][bold bright_cyan]░░░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░░░░░░░░░░░░░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ╚═══════════════╝[/bold white]"""

ROBOT_WINK = """\
[bold red]        ●[/bold red]
[bold red]        │[/bold red]
[bold white]  ╔═══════════════╗[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░░░░░░░░░░░░░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]╔═════╗[/bold white][bold bright_cyan]░[/bold bright_cyan][bold white]╔═════╗[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░░░░░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░░─░░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░░░░░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░░░░░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]╚═════╝[/bold white][bold bright_cyan]░[/bold bright_cyan][bold white]╚═════╝[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░░░[/bold bright_cyan][bold white]╰───────╯[/bold white][bold bright_cyan]░░░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░░░░░░░░░░░░░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ╚═══════════════╝[/bold white]"""

ROBOT_HAPPY = """\
[bold red]        ●[/bold red]
[bold red]        │[/bold red]
[bold white]  ╔═══════════════╗[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░░░░░░░░░░░░░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]╔═════╗[/bold white][bold bright_cyan]░[/bold bright_cyan][bold white]╔═════╗[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░░░░░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░░░░░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░░░░░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░░░░░[/bold bright_cyan][bold white]║[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]╚═════╝[/bold white][bold bright_cyan]░[/bold bright_cyan][bold white]╚═════╝[/bold white][bold bright_cyan]░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░░[/bold bright_cyan][bold white]╰─────────╯[/bold white][bold bright_cyan]░░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ║[/bold white][bold bright_cyan]░░░░░░░░░░░░░░░[/bold bright_cyan][bold white]║[/bold white]
[bold white]  ╚═══════════════╝[/bold white]"""

SEQUENCE = [
    (ROBOT_OPEN,  0.8),
    (ROBOT_BLINK, 0.2),
    (ROBOT_OPEN,  0.5),
    (ROBOT_WINK,  0.3),
    (ROBOT_OPEN,  0.5),
    (ROBOT_BLINK, 0.2),
    (ROBOT_OPEN,  0.5),
    (ROBOT_HAPPY, 0.8),
    (ROBOT_OPEN,  1.1),
]

def build_frame(robot: str) -> Align:
    logo_panel = Panel(
        f"{LOGO}\n\n[dim italic]{TAGLINE}[/dim italic]",
        border_style="bright_cyan",
        padding=(2, 4)
    )
    return Align.center(
        Columns(
            [logo_panel, Align.center(robot, vertical="middle")],
            equal=False,
            expand=False,
            align="center"
        ),
        vertical="middle"
    )

async def _animate():
    with Live(console=console, refresh_per_second=10) as live:
        for frame, duration in SEQUENCE:
            live.update(build_frame(frame))
            await asyncio.sleep(duration)

def print_logo():
    asyncio.run(_animate())

    console.clear()
    console.print()

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
