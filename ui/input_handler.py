# Routes user input — separates slash commands from real requests
# Graph indexing is now automatic - no user-facing commands

COMMANDS = {
    "/files":   "list_files",
    "/reset":   "reset_session",
    "/help":    "show_help",
    "/session": "show_session",
    "/graph-clear": "graph_clear",
    "/spec load":   "spec_load",
    "/spec show":   "spec_show",
    "/spec clear":  "spec_clear",
    "/spec":        "spec_show",   # bare /spec → show current spec
    "/exit":    "exit",
}

def handle_input(text: str) -> tuple[str, str]:
    text = text.strip()

    # check if input is a slash command
    for cmd, action in COMMANDS.items():
        if text.startswith(cmd):
            return ("command", action)
        
    # # Check longest-match first so "/spec load" beats "/spec"
    # for cmd in sorted(COMMANDS, key=len, reverse=True):
    #     if text.lower().startswith(cmd):
    #         return ("command", COMMANDS[cmd])

    # otherwise it's a real request
    return ("message", text)