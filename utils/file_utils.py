# Safe file I/O helpers — read and write files without crashing the system

from utils.logger import logger

def safe_read(path: str, default: str = "") -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Could not read {path}: {e}")
        return default  # return empty string instead of crashing

def safe_write(path: str, content: str) -> bool:
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return True  # success
    except Exception as e:
        logger.error(f"Could not write {path}: {e}")
        return False  # failure — caller decides what to do