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
from tools.read_spec import read_spec

# Orchestrator tools — only read_spec; orchestrator calls it during plan()
ORCHESTRATOR_TOOLS = [read_spec]

# Coder tools — write/edit/read + auto-index + path resolution tools + test runner
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
EXPLORER_TOOLS = [read_file, list_files, web_search, graph_code_search]

# All tools — for reference
ALL_TOOLS = ORCHESTRATOR_TOOLS + CODER_TOOLS + EXPLORER_TOOLS
