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
    try:
        from context.graph_index import query_context
    except ImportError as e:
        return (
            "Graph RAG dependencies missing. Install with: "
            f"pip install neo4j sentence-transformers ({e})"
        )
    return query_context(q, k=5)
