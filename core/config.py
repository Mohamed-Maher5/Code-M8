# core/config.py

import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Base URL — both models via OpenRouter
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Models
HUNTER_MODEL  = "openrouter/hunter-alpha"
MINIMAX_MODEL = "minimax/minimax-m2.5"

# Paths
WORKSPACE_PATH = "./workspace"
SESSIONS_PATH  = "./sessions"

# Model context limits
HUNTER_CONTEXT_WINDOW  = 1_000_000   # hunter-alpha
MINIMAX_CONTEXT_WINDOW = 196_608     # minimax-m2.5

# Hunter limits — Orchestrator + Explorer
HUNTER_MAX_TOKENS        = int(HUNTER_CONTEXT_WINDOW * 0.80)   # 800000
HUNTER_MAX_OUTPUT_TOKENS = int(HUNTER_CONTEXT_WINDOW * 0.15)   # 150000

# MiniMax limits — Coder
MINIMAX_MAX_TOKENS        = int(MINIMAX_CONTEXT_WINDOW * 0.80)  # 157286
MINIMAX_MAX_OUTPUT_TOKENS = int(MINIMAX_CONTEXT_WINDOW * 0.15)  # 29491

# File size limit
MAX_FILE_SIZE_KB = 50000

# Dirs to never scan or list
BLOCKED_DIRS = {
    "__pycache__", ".git", "node_modules",
    ".venv", "venv", "sessions", ".mypy_cache",
    ".pytest_cache", "dist", "build", ".idea"
}

# Files to never send to the model
BLOCKED_FILES = {
    ".env", ".env.local",
    "*.key", "*.pem", "*.secret",
    "id_rsa", "id_rsa.pub",
    "credentials", "*.token"
}


TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".htm", ".css", ".scss",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env",
    ".md", ".txt", ".rst", ".csv", ".xml", ".sql", ".sh", ".bash",
    ".c", ".cpp", ".h", ".java", ".go", ".rs", ".rb", ".php",
    ".gitignore", ".dockerfile", ".makefile", ""
}
