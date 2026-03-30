# core/memory/__init__.py
# Enhanced memory system for Code-M8

from core.memory.entity_extractor import (
    extract_entities,
    extract_code_changes,
    detect_errors,
)

from core.memory.llm_extractor import (
    extract_with_llm,
    compact_turns_with_llm,
    analyze_relationships_with_llm,
)

from core.memory.memory_index import (
    MemoryIndex,
    get_memory_index,
    load_session_into_index,
)

from core.memory.compaction import (
    CompactionManager,
    get_compaction_manager,
)

from core.memory.retrieval import (
    retrieve_relevant_memory,
    build_memory_context_for_orchestrator,
    get_session_memory_summary,
)

__all__ = [
    # Regex-based extraction (legacy)
    "extract_entities",
    "extract_code_changes",
    "detect_errors",
    # LLM-based extraction
    "extract_with_llm",
    "compact_turns_with_llm",
    "analyze_relationships_with_llm",
    # Memory index
    "MemoryIndex",
    "get_memory_index",
    "load_session_into_index",
    # Compaction
    "CompactionManager",
    "get_compaction_manager",
    # Retrieval
    "retrieve_relevant_memory",
    "build_memory_context_for_orchestrator",
    "get_session_memory_summary",
]
