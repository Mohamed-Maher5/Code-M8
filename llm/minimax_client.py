# llm/minimax_client.py
# MiniMax M2.5 client — uses MiniMax M2.5 via OpenRouter with LangChain
# Used by: Coder agent

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from llm.base_client import BaseLLMClient
from core.config import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    MINIMAX_MODEL,
    MINIMAX_MAX_OUTPUT_TOKENS,
)
from utils.logger import logger


class MinimaxClient(BaseLLMClient):

    def __init__(self, system_prompt: str = "You are a helpful coding assistant."):
        self.system_prompt = system_prompt
        # initialize LangChain client with OpenRouter
        self.client = ChatOpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL,
            model=MINIMAX_MODEL,
            max_tokens=MINIMAX_MAX_OUTPUT_TOKENS,
            streaming=True,
        )
        self.model = MINIMAX_MODEL
        logger.info(f"MinimaxClient initialised — model: {self.model}")

    def _build_messages(self, prompt: str) -> list:
        # build system + user message list for LangChain
        return [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt),
        ]

    def complete(self, prompt: str) -> str:
        # send prompt and return full response as string
        try:
            logger.info(f"MinimaxClient.complete() called")
            response = self.client.invoke(self._build_messages(prompt))
            return response.content or ""
        except Exception as e:
            logger.error(f"MinimaxClient.complete() failed: {e}")
            raise

    def stream(self, prompt: str):
        # stream response token by token
        try:
            logger.info(f"MinimaxClient.stream() called")
            for chunk in self.client.stream(self._build_messages(prompt)):
                if chunk.content:
                    yield chunk.content
        except Exception as e:
            logger.error(f"MinimaxClient.stream() failed: {e}")
            raise