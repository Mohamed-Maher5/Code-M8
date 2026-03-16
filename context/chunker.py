# AST-aware code chunker — splits files into complete logical units
# never cuts mid-function or mid-class
# falls back to full file if parsing fails

import ast
from utils.logger import logger

def chunk_python(source: str, filename: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        logger.warning(f"Could not parse {filename}: {e} — returning full file")
        return [source]

    chunks = []
    lines  = source.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = node.lineno - 1
            end   = node.end_lineno
            body  = "\n".join(lines[start:end])
            chunks.append(f"# {filename} — {node.name}\n{body}")

    # if no functions or classes found — return full file
    return chunks if chunks else [source]


def chunk_file(content: str, filename: str) -> list[str]:
    # python files — AST chunking
    if filename.endswith(".py"):
        return chunk_python(content, filename)

    # all other files — return as single chunk
    # Phase 2: Tree-sitter will handle all languages
    return [f"# {filename}\n{content}"]