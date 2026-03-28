# Auto-index tool — automatically indexes workspace for the coding agent
# This tool is called internally by the coding agent when:
# - Creating a user request
# - Reading codebase from workspace

from langchain_core.tools import tool


@tool
def auto_index_workspace(workspace_path: str) -> str:
    """Automatically index the workspace codebase for semantic search.
    
    This tool is used internally by the coding agent to ensure the codebase
    is indexed before performing searches or when reading from the workspace.
    
    Args:
        workspace_path: Absolute path to the workspace directory
        
    Returns:
        str: Status message about the indexing operation
    """
    from context.graph_index import ensure_indexed
    
    if not workspace_path or not workspace_path.strip():
        return "No workspace path provided."
    
    try:
        indexed = ensure_indexed(workspace_path.strip())
        if indexed:
            return "Workspace indexing complete or already up-to-date."
        else:
            return (
                "Graph RAG is not configured or indexing failed. "
                "Set NEO4J_URI, NEO4J_USERNAME, and NEO4J_PASSWORD in .env "
                "to enable automatic codebase indexing."
            )
    except Exception as e:
        return f"Indexing failed: {e}"
