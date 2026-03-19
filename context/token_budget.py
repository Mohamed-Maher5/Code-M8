# context/token_budget.py
# Tracks token usage and trims chunks to fit within model limits

from core.config import HUNTER_MAX_TOKENS, MINIMAX_MAX_TOKENS, GROQ_MAX_TOKENS
from utils.logger import logger


def estimate_tokens(text: str) -> int:
    return len(text) // 4


def calculate_reserved(system_prompt: str = "", user_input: str = "") -> int:
    actual   = estimate_tokens(system_prompt) + estimate_tokens(user_input)
    reserved = int(actual * 1.2)
    return max(reserved, 500)


def trim_to_budget(
    chunks       : list[str],
    model        : str = "groq",
    system_prompt: str = "",
    user_input   : str = ""
) -> list[str]:

    reserved = calculate_reserved(system_prompt, user_input)

    if model == "groq":
        budget = GROQ_MAX_TOKENS - reserved
    elif model == "minimax":
        budget = MINIMAX_MAX_TOKENS - reserved
    else:
        budget = HUNTER_MAX_TOKENS - reserved

    kept  = []
    total = 0

    for chunk in chunks:
        tokens = estimate_tokens(chunk)
        if total + tokens > budget:
            trimmed_count = len(chunks) - len(kept)
            logger.warning(
                f"Token budget reached — "
                f"kept {len(kept)}/{len(chunks)} chunks — "
                f"trimmed {trimmed_count} chunks"
            )
            kept.append(
                f"[Note: {trimmed_count} chunks were trimmed due to token limits. "
                f"Ask for specific files if you need more context.]"
            )
            break
        kept.append(chunk)
        total += tokens

    logger.info(
        f"Token budget: {total}/{budget} used — "
        f"reserved: {reserved} — model: {model}"
    )
    return kept