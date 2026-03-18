# main.py
# Entry point — boots Code M8 and starts the terminal UI

from core_logic.loop  import run_turn
from ui.terminal_ui   import TerminalUI


def main():
    ui = TerminalUI(loop_fn=run_turn)
    ui.start()


if __name__ == "__main__":
    main()