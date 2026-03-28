# Code M8 🤖

**Your AI coding teammate — reads your code, writes what you need**

An AI assistant that lives in your terminal, reads your codebase, and writes production-ready code that fits your project — all on your machine.

---

## ✨ Features

### 🧠 **Intelligent Code Understanding**
- **Automatic Codebase Indexing** - Your codebase is automatically indexed when you work
- **Semantic Code Search** - Find code by meaning, not just keywords
- **Graph-Based Retrieval** - Understands relationships between files and functions
- **Smart Context** - Knows your project structure and coding patterns

### ⚡ **Production-Ready Coding**
- **Writes Clean Code** - Generates code that matches your project's style
- **Automatic Verification** - Reads back files to ensure changes landed correctly
- **Incremental Updates** - Only re-indexes changed files for fast performance
- **Multi-File Changes** - Handles complex refactors across multiple files

### 🔍 **Deep Code Exploration**
- **Read-Only Analysis** - Explores your codebase without modifying anything
- **Architecture Understanding** - Explains how your system works
- **Pattern Location** - Finds where patterns and features are implemented
- **Dependency Tracking** - Knows which files import which modules

### 🗄️ **Graph RAG Integration** (Optional)
- **Neo4j-Powered** - Stores code structure in a graph database
- **Vector Search** - Semantic similarity search over your code
- **Graph Expansion** - Follows relationships to find related code
- **Auto-Cleanup** - Automatically removes stale data

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+** (tested on Python 3.11-3.14)
- **pip** or **uv** for package management
- **Git** (for cloning)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/Code-M8.git
   cd Code-M8
   ```

2. **Create a virtual environment:**
   ```bash
   # Using venv
   python -m venv venv
   venv\Scripts\activate  # Windows
   source venv/bin/activate  # macOS/Linux

   # Or using uv (recommended)
   uv venv
   uv activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables:**
   ```bash
   # Create .env file
   cp .env.example .env
   ```

   Edit `.env` with your API keys:
   ```env
   # Required: Groq API key (for Explorer & Coder models)
   GROQ_API_KEY=your_groq_api_key_here

   # Optional: OpenRouter API key (for alternative models)
   OPENROUTER_API_KEY=your_openrouter_api_key_here

   # Optional: Graph RAG (Neo4j) configuration
   NEO4J_URI=neo4j://localhost:7687
   NEO4J_USERNAME=neo4j
   NEO4J_PASSWORD=your_neo4j_password
   ```

5. **Create workspace directory:**
   ```bash
   mkdir workspace
   ```

   Copy your codebase into `workspace/`:
   ```bash
   cp -r /path/to/your/project/* workspace/
   ```

6. **Run Code M8:**
   ```bash
   python main.py
   ```

---

## 💬 Usage

### Basic Commands

Once running, you can interact with Code M8:

```
❯ read my codebase and explain the architecture
```

```
❯ where is the authentication configured?
```

```
❯ add a login function to auth.py
```

```
❯ fix the bug in the parser module
```

### Slash Commands

| Command | Description |
|---------|-------------|
| `/files` | List all files in workspace |
| `/reset` | Clear conversation history |
| `/session` | Show current session info |
| `/graph-clear` | ⚠️ Clear graph database (requires confirmation) |
| `/help` | Show all available commands |
| `/exit` | Quit Code M8 |

### Example Session

```
╭─ commands ─────────────────────────────────────╮
│ /files       → list workspace files            │
│ /reset       → clear session history           │
│ /session     → show session info               │
│ /graph-clear → ⚠️ wipe graph DB               │
│ /help        → show this help                  │
│ /exit        → quit                            │
╰────────────────────────────────────────────────╯

❯ read my codebase and find the database connection

  🧠  ORCHESTRATOR  planning  ⠋  5.2s
  🔍  EXPLORER  reading files  ⠙  10.3s

FINDINGS:
file: src/database.py
anchor: class DatabaseConnection:
context: Handles all database connections
last_safe_line: return connection

❯ add a method to close the connection

  🧠  ORCHESTRATOR  planning  ⠹  3.1s
  ⚡  CODER  writing code  ⠸  8.5s

CHANGES:
- edited: src/database.py
```

---

## 🗄️ Graph RAG (Optional)

Code M8 includes optional Graph RAG (Retrieval-Augmented Generation) for semantic code search.

### What It Does

- **Indexes your codebase** into a Neo4j graph database
- **Enables semantic search** - find code by meaning, not just keywords
- **Understands relationships** - knows which files import which modules
- **Auto-maintains** - automatically cleans up stale data

### When It's Used

- **Automatic Indexing** - Your codebase is indexed automatically when:
  - Explorer reads the codebase
  - Coder writes/edits files
  - Workspace changes are detected

- **Semantic Search** - Used when you ask:
  - "Where is authentication configured?"
  - "How does the parser work?"
  - "Find all database connections"

### Installation

Graph RAG dependencies are included in `requirements.txt`. To enable:

1. **Install Neo4j** (Community Edition is free):
   ```bash
   # Docker (recommended)
   docker run \
     --name neo4j \
     -p 7474:7474 -p 7687:7687 \
     -e NEO4J_AUTH=neo4j/your_password \
     neo4j:5
   ```

2. **Configure in `.env`:**
   ```env
   NEO4J_URI=neo4j://localhost:7687
   NEO4J_USERNAME=neo4j
   NEO4J_PASSWORD=your_password
   ```

3. **Run Code M8:**
   ```bash
   python main.py
   ```

   Graph indexing happens automatically on first request!

### Manual Graph Management

```bash
# Clear graph database (force re-index)
❯ /graph-clear
⚠️  CONFIRM GRAPH CLEAR
Type 'yes' to confirm: yes
✓ Graph index cleared (all nodes removed).
```

---

## 🏗️ Architecture

### Agents

| Agent | Role | Tools |
|-------|------|-------|
| **🧠 Orchestrator** | Plans and coordinates | Planning, synthesis |
| **🔍 Explorer** | Reads and analyzes codebase | `read_file`, `list_files`, `graph_code_search`, `web_search` |
| **⚡ Coder** | Writes and edits code | `write_file`, `edit_file`, `read_file` |

### Tools

- **`read_file`** - Read file contents
- **`write_file`** - Create or replace entire file
- **`edit_file`** - Replace specific code block
- **`list_files`** - List workspace files
- **`web_search`** - Search the web (DuckDuckGo)
- **`graph_code_search`** - Semantic code search (Graph RAG)
- **`auto_index_workspace`** - Auto-index workspace (Coder only)

### Context Building

- **Simple Context** - Keyword-based relevance scoring
- **Graph Context** - Vector similarity + graph expansion
- **Token Budget** - Respects model context limits (Groq: 128K, MiniMax: 196K)

---

## ⚙️ Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | ✅ Yes | Groq API key for models |
| `OPENROUTER_API_KEY` | ⚠️ Optional | OpenRouter API key (alternative) |
| `NEO4J_URI` | ⚠️ Optional | Neo4j connection URI |
| `NEO4J_USERNAME` | ⚠️ Optional | Neo4j username |
| `NEO4J_PASSWORD` | ⚠️ Optional | Neo4j password |
| `GROQ_MODEL` | ⚠️ Optional | Groq model (default: `qwen/qwen3-32b`) |

### Model Configuration

Edit `core/config.py` to change models:

```python
# Groq model (default)
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3-32b")

# OpenRouter models (alternative)
HUNTER_MODEL = "qwen/qwen3-coder:free"
MINIMAX_MODEL = "minimax/minimax-m2.5"
```

---

## 📊 Performance

### Indexing Speed

| Scenario | Time | Notes |
|----------|------|-------|
| **First index** | 30-60s | Full codebase index |
| **Unchanged** | 0.1s | Hash-based skip (304x faster!) |
| **1 file changed** | 1-5s | Incremental index |
| **50% changed** | 15-30s | Partial re-index |

### Cleanup

- **Auto-cleanup** runs after every index operation
- **Orphan removal** takes 0.5-1s
- **Full clear** takes 0.5s

---

## 🛠️ Development

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
pytest tests/
```

### Code Quality

```bash
# Install linting tools
pip install black flake8 mypy

# Format code
black .

# Lint code
flake8 .

# Type checking
mypy .
```

### Project Structure

```
Code-M8/
├── agents/           # Agent implementations
│   ├── base_agent.py
│   ├── orchestrator.py
│   ├── explorer.py
│   └── coder.py
├── context/          # Context building & Graph RAG
│   ├── graph_*.py    # Graph RAG modules
│   ├── chunker.py
│   └── context_builder.py
├── core/             # Core types and config
├── core_logic/       # Main execution loop
├── tools/            # Tool implementations
├── ui/               # Terminal UI
├── utils/            # Utilities
├── workspace/        # Your codebase (gitignored)
└── sessions/         # Session history (gitignored)
```

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Code Style

- **Black** for formatting
- **Flake8** for linting
- **MyPy** for type checking
- **PEP 8** style guide

---

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **LangChain** - Framework for agent orchestration
- **LangGraph** - Graph-based agent workflows
- **Groq** - Fast inference for LLMs
- **Neo4j** - Graph database for RAG
- **Qwen** - Open-source LLM models

---

## 📞 Support

- **Issues:** [GitHub Issues](https://github.com/YOUR_USERNAME/Code-M8/issues)
- **Discussions:** [GitHub Discussions](https://github.com/YOUR_USERNAME/Code-M8/discussions)
- **Email:** your.email@example.com

---

## 🎯 Roadmap

- [ ] Tree-sitter for multi-language support
- [ ] Real-time file watching
- [ ] Multi-workspace support
- [ ] Custom tool creation
- [ ] Plugin system
- [ ] Web UI (optional)
- [ ] Test generation
- [ ] Code review mode

---

**Built with ❤️ by Your Name**

*Code M8 - Your AI coding teammate*
