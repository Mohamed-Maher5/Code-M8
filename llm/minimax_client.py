# MiniMax client — uses MiniMax M2.5 via OpenRouter with LangChain
# Used by: Coder agent

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from llm.base_client import BaseLLMClient
from core.config import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    MINIMAX_MODEL,
    MINIMAX_MAX_OUTPUT_TOKENS
)
from utils.logger import logger

class MinimaxClient(BaseLLMClient):

    def __init__(self):
        # initialize LangChain client with OpenRouter
        self.client = ChatOpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL,
            model=MINIMAX_MODEL,
            max_tokens=MINIMAX_MAX_OUTPUT_TOKENS,
            streaming=True
        )
        self.model = MINIMAX_MODEL

    def complete(self, prompt: str) -> str:
        # send prompt and return full response
        try:
            logger.info(f"MinimaxClient sending prompt to {self.model}")
            response = self.client.invoke([
                HumanMessage(content=prompt)
            ])
            return response.content
        except Exception as e:
            logger.error(f"MinimaxClient error: {e}")
            return ""

    def stream(self, prompt: str):
        # stream response token by token
        try:
            logger.info(f"MinimaxClient streaming from {self.model}")
            return self.client.stream([
                HumanMessage(content=prompt)
            ])
        except Exception as e:
            logger.error(f"MinimaxClient stream error: {e}")
            return None