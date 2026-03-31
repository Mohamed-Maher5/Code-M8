# tools/tool_registry.py
# Single place where all tools are registered
# Agents import from here — never define tools inline

from tools.write_file import write_file
from tools.edit_file import edit_file
from tools.read_file import read_file
from tools.list_files import list_files
from tools.web_search import web_search
from tools.graph_search import graph_code_search
from tools.auto_index import auto_index_workspace
from tools.run_test import run_test

# Coder tools — write/edit/read + auto-index + path resolution tools + test runner
# The auto_index tool ensures the workspace is indexed when the coding agent
# creates user requests or reads from the workspace
# list_files and graph_code_search help verify correct file paths before editing
CODER_TOOLS = [
    write_file,
    edit_file,
    read_file,
    list_files,
    graph_code_search,
    auto_index_workspace,
    run_test,
]

# Explorer tools — read + web + graph search for semantic code search
# Graph search is now enabled for smarter codebase exploration
EXPLORER_TOOLS = [read_file, list_files, web_search, graph_code_search]

# All tools — for reference
ALL_TOOLS = CODER_TOOLS + EXPLORER_TOOLS
