# llm/qwen_client.py
# Hunter-alpha client — uses Hunter-alpha via OpenRouter with LangChain
# Used by: Orchestrator and Explorer agents

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

    def __init__(self, system_prompt: str = "You are a helpful assistant."):
        self.system_prompt = system_prompt
        # initialize LangChain client with OpenRouter
        self.llm = ChatOpenAI(
            model=HUNTER_MODEL,
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url=OPENROUTER_BASE_URL,
            max_tokens=HUNTER_MAX_OUTPUT_TOKENS,
            streaming=False,
        )
        logger.info(f"QwenClient initialised — model: {HUNTER_MODEL}")

    def _build_messages(self, prompt: str) -> list:
        # build system + user message list for LangChain
        return [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt),
        ]

    def complete(self, prompt: str) -> str:
        # send prompt and return full response as string
        logger.info("QwenClient.complete() called")
        try:
            messages = self._build_messages(prompt)
            response = self.llm.invoke(messages)
            result = response.content or ""
            logger.info(f"QwenClient.complete() — received {len(result)} chars")
            return result
        except Exception as e:
            logger.error(f"QwenClient.complete() failed: {e}")
            raise

    def stream(self, prompt: str):
        # stream response token by token
        logger.info("QwenClient.stream() called")
        try:
            messages = self._build_messages(prompt)
            for chunk in self.llm.stream(messages):
                if chunk.content:
                    yield chunk.content
        except Exception as e:
            logger.error(f"QwenClient.stream() failed: {e}")
            raise