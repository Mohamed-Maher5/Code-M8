# Assembles the final prompt from file chunks, history, and task instruction
# This is the ONLY place prompts are built — agents never build prompts inline

from context.chunker import chunk_file
from context.token_budget import trim_to_budget
from core.token_usage import estimate_tokens
from utils.logger import logger

# common words that mean nothing — ignore them
STOPWORDS = {
    "add",
    "the",
    "to",
    "a",
    "an",
    "in",
    "of",
    "for",
    "is",
    "it",
    "my",
    "we",
    "i",
    "and",
    "or",
    "with",
    "this",
    "that",
    "can",
    "do",
}


def sort_by_relevance(chunks: list[str], user_input: str) -> list[str]:
    # extract meaningful keywords only — ignore stopwords
    keywords = [
        word
        for word in user_input.lower().split()
        if word not in STOPWORDS and len(word) > 2
    ]

    if not keywords:
        return chunks  # no keywords — return as is

    def score(chunk: str) -> int:
        chunk_lower = chunk.lower()
        chunk_score = 0
        for word in keywords:
            # exact match — high score
            if word in chunk_lower:
                chunk_score += 2
            # partial match — lower score
            # "auth" matches "authentication", "authorize"
            if any(word in w for w in chunk_lower.split()):
                chunk_score += 1
        return chunk_score

    return sorted(chunks, key=score, reverse=True)


def build_prompt(
    task_instruction: str,
    file_index: dict,
    history: list,
    user_input: str = "",
    model: str = "hunter",
    relevant_files: list = None,
) -> str:

    # select which files to use
    files_to_use = relevant_files if relevant_files else list(file_index.keys())

    # build chunks from selected files
    all_chunks = []
    for path in files_to_use:
        if path in file_index:
            content = file_index[path].get("content", "")
            if content and content != "[file too large]":
                all_chunks.extend(chunk_file(content, path))

    # sort by relevance to user input
    if user_input:
        all_chunks = sort_by_relevance(all_chunks, user_input)

    # trim to fit token budget
    trimmed = trim_to_budget(
        all_chunks, model=model, system_prompt=task_instruction, user_input=user_input
    )

    # assemble file content block
    files_block = "\n\n".join(trimmed)

    # assemble history block — last 6 messages only
    history_block = "\n".join([f"{m['role']}: {m['content']}" for m in history[-6:]])

    # build final prompt
    prompt = f"""
                Recent conversation:
                {history_block}

                Project files:
                {files_block}

                Task: {task_instruction}
            """

    logger.info(f"Prompt built — {estimate_tokens(prompt)} tokens estimated")
    return prompt
