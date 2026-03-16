# Main terminal interface — handles input, displays output, manages the chat loop

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from ui.input_handler import handle_input
from ui.renderer import render_response
from ui.panels import print_logo
from utils.logger import logger
from context.file_loader import load_files
from core.config import WORKSPACE_PATH

console = Console()

class TerminalUI:

    def __init__(self, loop_fn):
        self.loop_fn = loop_fn

    def handle_command(self, action: str):
        if action == "show_help":
            console.print(Panel(
                "[bold]Available commands:[/bold]\n"
                "/files   — list workspace files\n"
                "/reset   — clear session history\n"
                "/session — show session info\n"
                "/help    — show this help\n"
                "/exit    — quit",
                title="Code M8 — Help",
                border_style="blue"
            ))
        elif action == "exit":
            console.print("[bold red]Goodbye![/bold red]")
            raise SystemExit
        elif action == "list_files":
            files = load_files(WORKSPACE_PATH)
            for path, meta in files.items():
                console.print(f"[dim]{path}[/dim] ({meta['language']}, {meta['size_kb']}kb)")
        elif action == "reset_session":
            console.print("[yellow]Session reset.[/yellow]")
        elif action == "show_session":
            console.print("[dim]Session info coming soon.[/dim]")

    def start(self):
        print_logo()

        while True:
            try:
                user_input = console.input("\n[bold green]>[/bold green] ").strip()

                if not user_input:
                    continue

                kind, value = handle_input(user_input)

                if kind == "command":
                    self.handle_command(value)
                else:
                    console.print("[dim]thinking...[/dim]")
                    response = self.loop_fn(value)
                    render_response(response)

            except KeyboardInterrupt:
                console.print("\n[bold red]Goodbye![/bold red]")
                break
            except SystemExit:
                break
            except Exception as e:
                logger.error(f"Error: {e}")
                console.print(f"[red]Error: {e}[/red]")