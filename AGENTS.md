# AGENTS.md - Guidelines for AI Agents

This file provides guidance for AI coding agents operating in this repository.

---

## 1. Build / Lint / Test Commands

### Installation
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### Running the Application
```bash
# Start the terminal UI
python -m ui.terminal_ui

# Or run directly
python ui/terminal_ui.py
```

### Running Tests
```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run all tests
pytest tests/

# Run a specific test file
pytest tests/test_memory.py

# Run a specific test function
pytest tests/test_memory.py::test_entity_extraction -v

# Run with coverage
pytest tests/ --cov=. --cov-report=term-missing
```

### Code Quality
```bash
# Install linting tools
pip install black flake8 mypy

# Format code (required before commit)
black .

# Lint code
flake8 .

# Type checking
mypy .

# All checks at once
black . && flake8 . && mypy .
```

---

## 2. Code Style Guidelines

### Imports
- Use absolute imports: `from core.config import SESSIONS_PATH`
- Group imports in this order:
  1. Standard library (`os`, `json`, `typing`)
  2. Third-party (`langchain`, `pydantic`, `neo4j`)
  3. Local application (`core.*`, `agents.*`, `tools.*`)
- Within each group, sort alphabetically

### Formatting
- Use **Black** for automatic formatting (line length: 88)
- Maximum line length: 88 characters
- Use f-strings for string formatting
- Use underscores for long numbers: `1_000_000`

### Types
- Use **TypedDict** for dictionary types with known keys
- Use **dataclasses** for simple data containers
- Use **Enums** for fixed sets of values
- Prefer explicit types over `Any`
- Use `Optional[X]` instead of `X | None` for compatibility

### Naming Conventions
- **Files**: snake_case (`session_manager.py`)
- **Classes**: PascalCase (`class AgentName`)
- **Functions/variables**: snake_case (`get_session_id`)
- **Constants**: UPPER_SNAKE_CASE (`MAX_FILE_SIZE_KB`)
- **Private functions**: prefix with underscore (`_private_func`)

### Error Handling
- Use try/except blocks with specific exception types
- Log errors with appropriate level: `logger.error(f"Failed: {e}")`
- Never expose secrets in error messages
- Provide user-friendly error messages in the UI

### Docstrings
- Use Google-style docstrings for public functions:
```python
def get_session_id() -> str:
    """Returns the current session ID.
    
    Returns:
        The session ID string.
    """
```

### Type Annotations
```python
# Good
def process_turn(user_input: str, history: List[Dict[str, Any]]) -> str:
    """Process a single turn."""
    pass

# Avoid
def process_turn(user_input, history):  # No types
```

---

## 3. Project Structure

```
Code-M8/
├── agents/              # Agent implementations (LangGraph)
│   ├── base_agent.py    # Base class with ReAct pattern
│   ├── orchestrator.py  # Planning agent
│   ├── explorer.py      # Code search/explore agent
│   └── coder.py         # Code generation agent
├── context/             # Graph RAG & context building
│   ├── graph_config.py  # Neo4j & embedding setup
│   ├── graph_index.py   # Code indexing
│   ├── graph_search.py  # Semantic search
│   └── chunker.py       # File chunking
├── core/                # Core utilities
│   ├── config.py        # Configuration constants
│   ├── types.py         # Type definitions
│   └── session_manager.py  # Session persistence
├── core_logic/         # Main execution
│   ├── loop.py          # Main turn loop
│   ├── dispatcher.py    # Agent dispatching
│   └── synthesizer.py  # Response synthesis
├── tools/               # Tool implementations
│   ├── tool_registry.py # Tool definitions
│   ├── file_operations.py
│   └── graph_search.py
├── ui/                  # Terminal UI
│   └── terminal_ui.py
├── sessions/            # Session history (gitignored)
├── workspace/           # User code (gitignored)
└── tests/               # Test files
```

---

## 4. Key Patterns

### Agent Pattern (LangGraph ReAct)
```python
class BaseAgent(ABC):
    def __init__(self, llm: Any, agent_name: AgentName):
        self.llm = llm
        self.name = agent_name
        self._graph = self._build_graph()
```

### Memory Extraction
```python
# LLM-based extraction replaces regex
from core.memory.llm_extractor import extract_with_llm

memory = extract_with_llm(llm, user_message, results, final_answer)
```

### Session Management
```python
from core.session_manager import save_turn, load_history

# Save turn with full memory
save_turn(user_message, all_results, final_answer)

# Load recent history
history = load_history(last_n=6)
```

---

## 5. Common Tasks

### Adding a New Tool
1. Add tool function in `tools/` directory
2. Register in `tools/tool_registry.py`
3. Add to appropriate agent's `tools` property

### Adding a New Agent
1. Create agent in `agents/` using `BaseAgent`
2. Define `system_prompt`, `tools`, `build_todos`
3. Add to `core_logic/loop.py` initialization

### Modifying Memory System
- Entity extraction: `core/memory/llm_extractor.py`
- Semantic index: `core/memory/memory_index.py`
- Compaction: `core/memory/compaction.py`
- Retrieval: `core/memory/retrieval.py`

---

## 6. Important Notes

- **Workspace is gitignored** - Place test code in `workspace/`
- **Sessions are gitignored** - Session data in `sessions/`
- **Neo4j optional** - Set `NEO4J_URI`, `NEO4J_PASSWORD` in `.env`
- **API keys** - Use `.env` file with `GROQ_API_KEY`
- **Python 3.10+** required (tested on 3.11-3.14)
