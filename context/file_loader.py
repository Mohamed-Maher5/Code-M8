# Scans the workspace and builds a structured index of every file
# Enforces workspace boundary — never loads files outside workspace
# Blocks sensitive files from being sent to the model

import os
import fnmatch
from utils.language_detect import detect_language
from utils.file_utils import safe_read
from core.config import MAX_FILE_SIZE_KB, WORKSPACE_PATH

# folders that should never be scanned
BLOCKED_DIRS = [
    "__pycache__", ".git", "node_modules",
    ".venv", "venv", "sessions"
]

# files that should never be sent to the model
BLOCKED_FILES = [
    ".env", ".env.local", ".env.*",
    "*.key", "*.pem", "*.secret",
    "id_rsa", "id_rsa.pub",
    "credentials", "*.token"
]

def is_blocked_file(filename: str) -> bool:
    # check if file matches any blocked pattern
    for pattern in BLOCKED_FILES:
        if fnmatch.fnmatch(filename, pattern):
            return True
    return False

def is_within_workspace(path: str, workspace: str) -> bool:
    # prevent directory traversal attacks
    # makes sure we never read outside the workspace folder
    real_path      = os.path.realpath(path)
    real_workspace = os.path.realpath(workspace)
    return real_path.startswith(real_workspace)

def load_files(workspace: str = WORKSPACE_PATH) -> dict:
    index = {}

    for root, dirs, files in os.walk(workspace):

        # skip blocked folders
        dirs[:] = [d for d in dirs if d not in BLOCKED_DIRS]

        for file in files:

            # skip blocked files — never send to model
            if is_blocked_file(file):
                continue

            path = os.path.join(root, file)

            # enforce workspace boundary
            if not is_within_workspace(path, workspace):
                continue

            size_kb = os.path.getsize(path) / 1024

            index[path] = {
                "size_kb":  round(size_kb, 2),
                "language": detect_language(file),
                "content":  safe_read(path) if size_kb < MAX_FILE_SIZE_KB
                            else "[file too large]"
            }

    return index