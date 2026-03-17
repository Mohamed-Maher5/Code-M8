# Routes user input — separates slash commands from real requests

COMMANDS = {
    "/files":   "list_files",
    "/reset":   "reset_session",
    "/help":    "show_help",
    "/session": "show_session",
    "/exit":    "exit",
}

def handle_input(text: str) -> tuple[str, str]:
    text = text.strip()

    # check if input is a slash command
    for cmd, action in COMMANDS.items():
        if text.startswith(cmd):
            return ("command", action)

    # otherwise it's a real request
    return ("message", text)