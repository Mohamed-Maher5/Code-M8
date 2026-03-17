# Renders LLM output — markdown, code blocks, diffs

from rich.console import Console
from rich.syntax import Syntax
from rich.markdown import Markdown
from utils.language_detect import detect_language

console = Console()

def render_response(text: str):
    # render markdown formatted response
    console.print(Markdown(text))

def render_code(code: str, filename: str = "") -> None:
    # render syntax highlighted code
    lang = detect_language(filename) if filename else "python"
    console.print(Syntax(
        code,
        lang,
        theme="monokai",
        line_numbers=True
    ))

def render_diff(diff: str) -> None:
    # render colored diff — green added, red removed
    console.print(Syntax(
        diff,
        "diff",
        theme="monokai"
    ))