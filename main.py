# from agents.explorer import Explorer
# from core.types import make_task
# from langchain_openai import ChatOpenAI
# from core import config
# from agents.orchestrator import Orchestrator
# from agents.coder import Coder
# llm = ChatOpenAI(
#     api_key  = config.get_api_key(),
#     base_url = config.OPENROUTER_BASE_URL,
#     model    = config.HUNTER_MODEL,
# )
# explorer = Explorer(llm=llm)
# # task     = make_task("explorer", "tell me files about api and backend  and explain what it does and if you dont found it tell what is there in dir ")
# # result   = explorer.run(task)
# # print(result["output"])
# coder = Coder(llm=llm)
# task     = make_task("coder", "tell me files about api and backend  and explain what it does and if you dont found it tell what is there in dir then make call it maher.py then do hello world code in it ")
# result   = coder.run(task)
# print(result["output"])
# Entry point — boots Code M8 and starts the terminal UI

from core_logic.loop import run_turn
from ui.terminal_ui import TerminalUI

def main():
    ui = TerminalUI(loop_fn=run_turn)
    ui.start()

if __name__ == "__main__":
    main()