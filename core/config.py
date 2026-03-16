import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Models
OPENROUTER_MODEL = "openrouter/hunter-alpha"

# Base URL
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Paths
WORKSPACE_PATH = "./workspace"
SESSIONS_PATH  = "./sessions"

# Limits
MAX_FILE_SIZE_KB = 150
MAX_TOKENS       = 12000