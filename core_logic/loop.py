# Main turn engine — loads workspace, builds prompt, streams response

from context.file_loader import load_files
from context.context_builder import build_prompt
from llm.minimax_client import MinimaxClient
from llm.stream_handler import handle_stream
from core.config import WORKSPACE_PATH
from utils.logger import logger

client = MinimaxClient()

def run_turn(user_input: str) -> str:
    logger.info(f"Turn started: {user_input}")

    # step 1 — load workspace files
    file_index = load_files(WORKSPACE_PATH)
    logger.info(f"Loaded {len(file_index)} files from workspace")

    # step 2 — build prompt using context_builder
    prompt = build_prompt(
        task_instruction=user_input,
        file_index=file_index,
        history=[],           # empty until session_manager is ready
        user_input=user_input,
        model="minimax"
    )

    # step 3 — stream response
    print("\nthinking...\n")
    stream = client.stream(prompt)
    response = handle_stream(stream)

    logger.info("Turn completed")
    return response