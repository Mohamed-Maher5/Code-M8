# Abstract base interface — all LLM clients must implement these methods
# Agents import this type, never the concrete clients directly

from abc import ABC, abstractmethod

class BaseLLMClient(ABC):

    @abstractmethod
    def complete(self, prompt: str) -> str:
        # send prompt, return full response as string
        pass

    @abstractmethod
    def stream(self, prompt: str):
        # send prompt, return streaming response
        pass
