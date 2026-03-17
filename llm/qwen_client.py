# llm/qwen_client.py
# Qwen model client — built on LangChain, routed through OpenRouter
import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from dotenv import load_dotenv
from llm.base_client import BaseLLMClient
from core.config import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    HUNTER_MODEL,
    HUNTER_MAX_OUTPUT_TOKENS,
)
from utils.logger import logger

load_dotenv()


class QwenClient(BaseLLMClient):
    """
    Wraps Qwen (via OpenRouter) behind the BaseLLMClient interface.
    Uses LangChain's ChatOpenAI under the hood.
    """

    def __init__(self, system_prompt: str = "You are a helpful  assistant."):
        self.system_prompt = system_prompt

        # LangChain ChatOpenAI — pointed at OpenRouter
        self.llm = ChatOpenAI(
            model=HUNTER_MODEL,
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url=OPENROUTER_BASE_URL,
            max_tokens=HUNTER_MAX_OUTPUT_TOKENS,
            streaming=False,         # default off; stream() flips it per-call
        )
        logger.info(f"QwenClient (LangChain) initialised — model: {HUNTER_MODEL}")

    # ------------------------------------------------------------------
    # Build the LangChain message list
    # ------------------------------------------------------------------
    def _build_messages(self, prompt: str) -> list:
        return [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt),
        ]

    # ------------------------------------------------------------------
    # complete() — full response returned as a plain string
    # ------------------------------------------------------------------
    def complete(self, prompt: str) -> str:
        logger.info("QwenClient.complete() called")
        try:
            messages = self._build_messages(prompt)
            response = self.llm.invoke(messages)          # LangChain invoke
            result = response.content or ""
            logger.info(f"QwenClient.complete() — received {len(result)} chars")
            return result

        except Exception as e:
            logger.error(f"QwenClient.complete() failed: {e}")
            raise

    # ------------------------------------------------------------------
    # stream() — yields text chunks as they arrive
    # ------------------------------------------------------------------
    def stream(self, prompt: str):
        logger.info("QwenClient.stream() called")
        try:
            messages = self._build_messages(prompt)
            # LangChain .stream() yields AIMessageChunk objects
            for chunk in self.llm.stream(messages):
                if chunk.content:
                    yield chunk.content

        except Exception as e:
            logger.error(f"QwenClient.stream() failed: {e}")
            raise