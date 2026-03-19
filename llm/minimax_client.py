# llm/minimax_client.py
# Groq client — uses Groq models via LangChain
# Used by: all agents (active provider)

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from llm.base_client import BaseLLMClient
from core.config import (
    GROQ_API_KEY,
    GROQ_MODEL,
    GROQ_MAX_OUTPUT_TOKENS,
)
from utils.logger import logger


class GroqClient(BaseLLMClient):

    def __init__(self, system_prompt: str = "You are a helpful coding assistant."):
        self.system_prompt = system_prompt
        self.client = ChatGroq(
            api_key      = GROQ_API_KEY,
            model        = GROQ_MODEL,
            max_tokens   = GROQ_MAX_OUTPUT_TOKENS,
            streaming    = True,
            model_kwargs = {"include_reasoning": False},
        )
        self.model = GROQ_MODEL
        logger.info(f"GroqClient initialised — model: {self.model}")

    def _build_messages(self, prompt: str) -> list:
        return [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt),
        ]

    def complete(self, prompt: str) -> str:
        try:
            logger.info("GroqClient.complete() called")
            response = self.client.invoke(self._build_messages(prompt))
            return response.content or ""
        except Exception as e:
            logger.error(f"GroqClient.complete() failed: {e}")
            raise

    def stream(self, prompt: str):
        try:
            logger.info("GroqClient.stream() called")
            for chunk in self.client.stream(self._build_messages(prompt)):
                if chunk.content:
                    yield chunk.content
        except Exception as e:
            logger.error(f"GroqClient.stream() failed: {e}")
            raise