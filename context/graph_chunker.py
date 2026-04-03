"""AST-based chunking for Python files with relationship extraction."""

import ast
import hashlib

import tiktoken

from context.graph_models import Chunk, File, Relationship

enc = tiktoken.get_encoding("cl100k_base")


def _make_chunk(file_path, node, lines, name_override=None):
    """Build a Chunk from an AST node."""
    name = name_override or f"{file_path}:{node.name}"
    code = "\n".join(lines[node.lineno - 1 : node.end_lineno])
    return Chunk(
        name=name,
        start_line=node.lineno,
        end_line=node.end_lineno,
        code=code,
        relationships=[],
        docstring=ast.get_docstring(node),
    )


def _extract_calls(node):
    relationships = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            try:
                target = n.func.id
            except AttributeError:
                try:
                    target = n.func.attr
                except AttributeError:
                    continue
            relationships.append(Relationship("calls", target))
    return relationships


def chunk_file(file_path, max_tokens=1500):
    """Chunk a Python file into AST-based units with relationships."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        return [], None

    lines = content.splitlines()

    chunks = []
    import_lines = []
    global_lines = []
    imported_modules = []

    file_hash = hashlib.md5(content.encode()).hexdigest()
    file_node = File(file_path, [], file_hash)

    for node in ast.iter_child_nodes(tree):

        if isinstance(node, (ast.Import, ast.ImportFrom)):
            import_lines.append("\n".join(lines[node.lineno - 1 : node.end_lineno]))

            if isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.append(node.module)
            else:
                imported_modules.append(node.names[0].name)

        elif isinstance(node, ast.Assign):
            global_lines.append("\n".join(lines[node.lineno - 1 : node.end_lineno]))

        elif isinstance(node, ast.ClassDef):
            chunk = _make_chunk(file_path, node, lines)
            token_count = len(enc.encode(chunk.code))

            if token_count > max_tokens:
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_name = f"{file_path}:{node.name}:{child.name}"
                        method_chunk = _make_chunk(file_path, child, lines, name_override=method_name)
                        method_chunk.relationships.extend(_extract_calls(child))
                        chunks.append(method_chunk)
            else:
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        chunk.relationships.append(
                            Relationship("has_method", f"{file_path}:{node.name}:{child.name}")
                        )
                for base in node.bases:
                    try:
                        chunk.relationships.append(Relationship("inherits", base.id))
                    except AttributeError:
                        pass
                chunks.append(chunk)

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            chunk = _make_chunk(file_path, node, lines)
            chunk.relationships.extend(_extract_calls(node))
            chunks.append(chunk)

    if import_lines:
        chunks.append(
            Chunk(
                name=f"{file_path}:imports",
                start_line=0,
                end_line=0,
                code="\n".join(import_lines),
            )
        )

    if global_lines:
        chunks.append(
            Chunk(
                name=f"{file_path}:globals",
                start_line=0,
                end_line=0,
                code="\n".join(global_lines),
            )
        )

    file_node.chunks = [c.name for c in chunks]
    file_node.imports_from = imported_modules

    return chunks, file_node
