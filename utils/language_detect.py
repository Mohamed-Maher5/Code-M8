# Maps file extensions to programming language names for syntax highlighting and context

EXTENSIONS = {
    ".py":    "python",
    ".js":    "javascript",
    ".ts":    "typescript",
    ".html":  "html",
    ".css":   "css",
    ".sh":    "bash",
    ".json":  "json",
    ".md":    "markdown",
    ".yaml":  "yaml",
    ".yml":   "yaml",
    ".txt":   "text",
    ".env":   "text",
    ".toml":  "toml",
    ".xml":   "xml",
    ".sql":   "sql",
}

def detect_language(filename: str) -> str:
    # extract extension from filename
    ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""
    
    # return language or plaintext if unknown
    return EXTENSIONS.get(ext.lower(), "plaintext")