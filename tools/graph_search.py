# LangChain tool — Neo4j graph + vector RAG over indexed Python code
# This tool is used internally by the coding agent for semantic code search

from langchain_core.tools import tool


@tool
def graph_code_search(query: str) -> str:
    """Search the indexed Python codebase using vector similarity plus graph-linked chunks (Neo4j).

    Use for higher-level questions: where something is implemented, how modules relate, or to
    get several relevant snippets before opening full files with read_file.

    The workspace is automatically indexed by the coding agent when needed.
    Only .py files are indexed. If Neo4j is not configured, this tool returns a short notice."""
    q = (query or "").strip()
    if not q:
        return "Provide a non-empty search query."

    # Try graph search first (uses HuggingFace API for embeddings)
    try:
        from context.graph_index import query_context

        result = query_context(q, k=5)
        print(f"Graph search result for '{q}': {result}")
        # Only return if we got meaningful results
        if (
            result
            and "not configured" not in result.lower()
            and "could not connect" not in result.lower()
            and "no matching chunks" not in result.lower()
        ):
            return result
    except Exception:
        pass

    # Fallback: simple file search
    try:
        from pathlib import Path
        import core.config as CONFIG

        workspace = Path(CONFIG.WORKSPACE_PATH).resolve()
        print(f"Performing simple file search for '{q}' in {workspace}...")
        results = []

        py_files = list(workspace.rglob("*.py"))
        py_files = [
            f
            for f in py_files
            if ".venv" not in str(f) and "node_modules" not in str(f)
        ]

        for py_file in py_files[:50]:
            try:
                content = py_file.read_text(errors="ignore")
                if q.lower() in content.lower():
                    rel_path = py_file.relative_to(workspace)
                    lines = content.split("\n")
                    matches = [
                        (i + 1, line)
                        for i, line in enumerate(lines)
                        if q.lower() in line.lower()
                    ]
                    if matches:
                        snippet = "\n".join(
                            f"  {i}: {line.strip()}" for i, line in matches[:5]
                        )
                        results.append(f"File: {rel_path}\n{snippet}\n")
            except Exception:
                continue

        if results:
            return f"Found {len(results)} files matching '{q}':\n\n" + "\n".join(
                results[:10]
            )
        else:
            return f"No files found matching '{q}'"
    except Exception as e:
        return f"Search failed: {e}"
