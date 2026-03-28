"""Context module - provides context building and graph-based code retrieval.

This module combines:
1. Simple prompt-based context building (chunker, context_builder, token_budget)
2. Graph-based RAG for code (graph_index, graph_search, graph_builder, graph_chunker)

The graph RAG functionality is automatically used by the coding agent when
indexing the codebase - no user-facing options required.
"""

# Simple context building (prompt-based)
from context.chunker import chunk_file
from context.context_builder import build_prompt
from context.token_budget import trim_to_budget, estimate_tokens

# Graph-based RAG (automatic indexing for coding agent)
from context.graph_index import (
    index_workspace,
    clear_graph_index,
    query_context,
    ensure_indexed,
    index_codebase,
)
from context.graph_search import retrieve_code_context, similarity_search, get_context
from context.graph_builder import build_graph, embd_and_store
from context.graph_chunker import chunk_file as graph_chunk_file
from context.graph_config import graph_rag_enabled, get_driver, get_embedding_model, close_driver
from context.graph_models import Relationship, Chunk, File

__all__ = [
    # Simple context building
    "chunk_file",
    "build_prompt",
    "trim_to_budget",
    "estimate_tokens",
    # Graph RAG - indexing
    "index_workspace",
    "clear_graph_index",
    "ensure_indexed",
    "index_codebase",
    # Graph RAG - search
    "query_context",
    "retrieve_code_context",
    "similarity_search",
    "get_context",
    # Graph RAG - building
    "build_graph",
    "embd_and_store",
    "graph_chunk_file",
    # Graph RAG - config
    "graph_rag_enabled",
    "get_driver",
    "get_embedding_model",
    "close_driver",
    # Graph RAG - models
    "Relationship",
    "Chunk",
    "File",
]
