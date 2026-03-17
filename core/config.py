

"""
config.py
=========
Single source of truth for every setting in the project.
All models route through OpenRouter.

Orchestrator + Explorer → Hunter Alpha (1M context)
Coder                   → MiniMax M2.5 (196K context)
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── API ───────────────────────────────────────────────────────────────────────
OPENROUTER_API_KEY  = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# ── Models ────────────────────────────────────────────────────────────────────
HUNTER_MODEL  = "openrouter/hunter-alpha"
MINIMAX_MODEL = "minimax/minimax-m2.5"

# ── Context windows ───────────────────────────────────────────────────────────
HUNTER_CONTEXT_WINDOW  = 1_000_000
MINIMAX_CONTEXT_WINDOW = 196_608

# ── Token limits ──────────────────────────────────────────────────────────────
HUNTER_MAX_TOKENS        = int(HUNTER_CONTEXT_WINDOW  * 0.80)   # 800_000
HUNTER_MAX_OUTPUT_TOKENS = int(HUNTER_CONTEXT_WINDOW  * 0.15)   # 150_000

MINIMAX_MAX_TOKENS        = int(MINIMAX_CONTEXT_WINDOW * 0.80)  # 157_286
MINIMAX_MAX_OUTPUT_TOKENS = int(MINIMAX_CONTEXT_WINDOW * 0.15)  # 29_491

# ── Paths ─────────────────────────────────────────────────────────────────────
WORKSPACE_PATH = os.getenv("WORKSPACE_PATH", "./workspace")
SESSIONS_PATH  = os.getenv("SESSIONS_PATH",  "./sessions")

# ── File limits ───────────────────────────────────────────────────────────────
MAX_FILE_SIZE_KB = 50_000

# ── Sandbox ───────────────────────────────────────────────────────────────────
SANDBOX_TIMEOUT_SEC = 15
SANDBOX_MEMORY_MB   = 256
SANDBOX_CPU_CORES   = 0.5
SANDBOX_PIDS_LIMIT  = 50
SANDBOX_IMAGE_NAME  = "ai_coding_assistant_sandbox"

# ── Agent behaviour ───────────────────────────────────────────────────────────
MAX_RETRIES = 3

IGNORED_DIRS = (
    ".git", "__pycache__", "node_modules",
    ".venv", "venv", "env",
    "dist", "build", ".next",
    "sandbox_tmp",
)

IGNORED_EXTENSIONS = (
    ".pyc", ".pyo", ".pyd",
    ".png", ".jpg", ".jpeg", ".gif",
    ".pdf", ".zip", ".tar", ".gz",
    ".lock", ".bin", ".exe", ".dll",
    ".DS_Store",
)

# ── Helper ────────────────────────────────────────────────────────────────────

def get_api_key() -> str:
    """
    Returns the OpenRouter API key.
    Raises ValueError immediately if missing so startup fails fast.
    """
    key = OPENROUTER_API_KEY.strip()
    if not key:
        raise ValueError(
            "Missing OPENROUTER_API_KEY. Add it to your .env file."
        )
    return key


def validate() -> None:
    """
    Called once by main.py at startup.
    Checks required settings before any agent runs.
    """
    errors = []

    if not OPENROUTER_API_KEY.strip():
        errors.append("OPENROUTER_API_KEY is not set in .env")

    for path in (WORKSPACE_PATH, SESSIONS_PATH):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            errors.append(f"Cannot create directory '{path}': {e}")

    if errors:
        raise ValueError(
            "Config errors:\n" + "\n".join(f"  → {e}" for e in errors)
        )


def summary() -> str:
    """Printed by main.py at startup so you can confirm settings."""
    return (
        f"\n{'═' * 48}\n"
        f"  AI Coding Assistant\n"
        f"{'═' * 48}\n"
        f"  Orchestrator/Explorer : {HUNTER_MODEL}\n"
        f"  Coder                 : {MINIMAX_MODEL}\n"
        f"  Workspace             : {WORKSPACE_PATH}\n"
        f"  Sessions              : {SESSIONS_PATH}\n"
        f"  Max retries           : {MAX_RETRIES}\n"
        f"  Sandbox timeout       : {SANDBOX_TIMEOUT_SEC}s\n"
        f"{'═' * 48}\n"
    )