# Handles streaming responses from LLM — prints tokens live
# and detects tool calls mid-stream

import re
from utils.logger import logger

def handle_stream(stream) -> str:
    full_response = ""

    try:
        for chunk in stream:
            # LangChain chunk — content is directly accessible
            delta = chunk.content or ""

            # print token immediately — live terminal output
            print(delta, end="", flush=True)

            # append to full response
            full_response += delta

        # newline after stream ends
        print()

    except Exception as e:
        logger.error(f"Stream error: {e}")

    return full_response


def extract_tool_calls(text: str) -> list:
    # finds all tool calls in the response
    # pattern: [TOOL: tool_name("args")]
    pattern = r"\[TOOL:\s*(\w+)\(([^)]*)\)\]"
    matches = re.findall(pattern, text)
    return matches