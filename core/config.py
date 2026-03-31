# core/config.py

import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ──────────────────────────────────────────────────────────────────

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ── Base URLs ─────────────────────────────────────────────────────────────────

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# ── Models — OpenRouter (kept, not active) ────────────────────────────────────

HUNTER_MODEL = "qwen/qwen3-coder:free"
MINIMAX_MODEL = "minimax/minimax-m2.5"

# ── Models — Groq (active) ────────────────────────────────────────────────────

GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3-32b")

# ── Paths ─────────────────────────────────────────────────────────────────────

# Optional graph RAG (Neo4j): set NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD in .env
# (loaded in context.graph_config). Graph indexing is automatic - the coding agent
# indexes *.py files under WORKSPACE_PATH when needed.

WORKSPACE_PATH = "./workspace"
SESSIONS_PATH = "./sessions"

# ── Context windows ───────────────────────────────────────────────────────────

HUNTER_CONTEXT_WINDOW = 1_000_000  # OpenRouter qwen3-coder
MINIMAX_CONTEXT_WINDOW = 196_608  # minimax-m2.5
GROQ_CONTEXT_WINDOW = int(os.getenv("GROQ_CONTEXT_WINDOW", "128000"))

# ── Token limits — OpenRouter Hunter (kept, not active) ───────────────────────

HUNTER_MAX_TOKENS = int(HUNTER_CONTEXT_WINDOW * 0.80)
HUNTER_MAX_OUTPUT_TOKENS = int(HUNTER_CONTEXT_WINDOW * 0.15)

# ── Token limits — OpenRouter MiniMax (kept, not active) ─────────────────────

MINIMAX_MAX_TOKENS = int(MINIMAX_CONTEXT_WINDOW * 0.80)
MINIMAX_MAX_OUTPUT_TOKENS = int(MINIMAX_CONTEXT_WINDOW * 0.15)

# ── Token limits — Groq (active) ─────────────────────────────────────────────

# Use conservative defaults for real-world tool-heavy coding turns.
# Input budget leaves room for retries/tool chatter, output budget is generous
# enough for full patches while avoiding context overflow.
GROQ_INPUT_RATIO = float(os.getenv("GROQ_INPUT_RATIO", "0.70"))
GROQ_OUTPUT_RATIO = float(os.getenv("GROQ_OUTPUT_RATIO", "0.20"))

GROQ_MAX_TOKENS = int(GROQ_CONTEXT_WINDOW * GROQ_INPUT_RATIO)
GROQ_MAX_OUTPUT_TOKENS = int(GROQ_CONTEXT_WINDOW * GROQ_OUTPUT_RATIO)

# Agent-level pre-invoke prompt budget (within input budget)
AGENT_MESSAGE_BUDGET_TOKENS = int(
    os.getenv("AGENT_MESSAGE_BUDGET_TOKENS", str(int(GROQ_MAX_TOKENS * 0.75)))
)

# Planning and retrieval context defaults (override via .env)
PLANNING_CONTEXT_MAX_TOKENS = int(os.getenv("PLANNING_CONTEXT_MAX_TOKENS", "3500"))
PLANNING_CONTEXT_MAX_CHARS = int(os.getenv("PLANNING_CONTEXT_MAX_CHARS", "18000"))
GRAPH_RETRIEVAL_MAX_TOKENS = int(os.getenv("GRAPH_RETRIEVAL_MAX_TOKENS", "8000"))
GRAPH_RETRIEVAL_MAX_CHARS = int(os.getenv("GRAPH_RETRIEVAL_MAX_CHARS", "32000"))

# Agent step limits
EXPLORER_MAX_STEPS = int(os.getenv("EXPLORER_MAX_STEPS", "3"))

# ── File size limit ───────────────────────────────────────────────────────────

MAX_FILE_SIZE_KB = 50000

# ── Workspace scanning ────────────────────────────────────────────────────────

BLOCKED_DIRS = {
    "__pycache__",
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "sessions",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".idea",
}

BLOCKED_FILES = {
    ".env",
    ".env.local",
    "*.key",
    "*.pem",
    "*.secret",
    "id_rsa",
    "id_rsa.pub",
    "credentials",
    "*.token",
}

TEXT_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".env",
    ".md",
    ".txt",
    ".rst",
    ".csv",
    ".xml",
    ".sql",
    ".sh",
    ".bash",
    ".c",
    ".cpp",
    ".h",
    ".java",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".gitignore",
    ".dockerfile",
    ".makefile",
    "",
}
