# tools/web_search.py
# Searches the web for documentation, packages, or external info
# Used by: Explorer agent (optional — when codebase context is not enough)

import os

from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun


@tool
def web_search(query: str) -> str:
    """
    Search the web for documentation, packages, or technical information.
    Returns a summary of the top results.
    query: plain text search query (e.g. 'Python JWT library example')
    """
    try:
        search = DuckDuckGoSearchRun()
        return search.run(query)
    except ImportError:
        return (
            "ERROR: web_search requires langchain-community.\n"
            "Install it with: uv pip install langchain-community duckduckgo-search"
        )
    except Exception as e:
        return f"ERROR: web_search failed — {e}"