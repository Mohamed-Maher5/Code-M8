# tools/tool_registry.py
# Single place where all tools are registered
# Agents import from here — never define tools inline

from tools.write_file  import write_file
from tools.edit_file   import edit_file
from tools.read_file   import read_file
from tools.list_files  import list_files
from tools.search_code import search_code
from tools.web_search  import web_search

# Coder tools — write only
CODER_TOOLS = [write_file, edit_file,read_file]

# Explorer tools — read + web
EXPLORER_TOOLS = [read_file, list_files, search_code, web_search]

# All tools — for reference
ALL_TOOLS = CODER_TOOLS + EXPLORER_TOOLS