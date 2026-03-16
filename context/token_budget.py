# Tracks token usage and trims chunks to fit within model limits
# dynamically calculates reserved tokens based on actual content
# tells the model what was cut so it can ask for more if needed

from core.config import HUNTER_MAX_TOKENS, MINIMAX_MAX_TOKENS
from utils.logger import logger

def estimate_tokens(text: str) -> int:
    # rough estimate — 4 characters per token
    return len(text) // 4

def calculate_reserved(system_prompt: str = "", user_input: str = "") -> int:
    # measure actual tokens needed for system prompt and user input
    actual = estimate_tokens(system_prompt) + estimate_tokens(user_input)
    # add 20% buffer for safety
    reserved = int(actual * 1.2)
    # minimum 500 tokens always reserved
    return max(reserved, 500)

def trim_to_budget(
    chunks: list[str],
    model: str = "hunter",
    system_prompt: str = "",
    user_input: str = ""
) -> list[str]:

    # calculate dynamic reserved based on actual content
    reserved = calculate_reserved(system_prompt, user_input)

    # pick the right limit based on model
    if model == "hunter":
        budget = HUNTER_MAX_TOKENS - reserved
    else:
        budget = MINIMAX_MAX_TOKENS - reserved

    kept  = []
    total = 0

    for chunk in chunks:
        tokens = estimate_tokens(chunk)

        # stop adding chunks when budget exceeded
        if total + tokens > budget:
            trimmed_count = len(chunks) - len(kept)
            logger.warning(
                f"Token budget reached — "
                f"kept {len(kept)}/{len(chunks)} chunks — "
                f"trimmed {trimmed_count} chunks"
            )
            # tell the model what was cut
            kept.append(
                f"[Note: {trimmed_count} chunks were trimmed due to token limits. "
                f"Ask for specific files if you need more context.]"
            )
            break

        kept.append(chunk)
        total += tokens

    logger.info(
        f"Token budget: {total}/{budget} used — "
        f"reserved: {reserved} — "
        f"model: {model}"
    )
    return kept