"""
LLM Provider Abstraction Layer
Supports both Anthropic Claude and local Ollama models
"""
import os
from typing import Optional, AsyncIterator, Dict, Any
from abc import ABC, abstractmethod
import anthropic
import httpx


class LLMProvider(ABC):
    """Abstract base class for LLM providers"""

    @abstractmethod
    async def generate_response(
        self,
        messages: list[Dict[str, str]],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0,
        stream: bool = False
    ) -> str | AsyncIterator[str]:
        """Generate a response from the LLM"""
        pass

    @abstractmethod
    async def generate_stream(
        self,
        messages: list[Dict[str, str]],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0
    ) -> AsyncIterator[str]:
        """Generate a streaming response from the LLM"""
        pass


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider"""

    def __init__(self, api_key: str):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = "claude-3-5-sonnet-20241022"

    async def generate_response(
        self,
        messages: list[Dict[str, str]],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0,
        stream: bool = False
    ) -> str:
        """Generate a response using Anthropic Claude"""
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages
        }

        if system:
            kwargs["system"] = system

        if stream:
            return self.generate_stream(messages, system, max_tokens, temperature)

        response = await self.client.messages.create(**kwargs)
        return response.content[0].text

    async def generate_stream(
        self,
        messages: list[Dict[str, str]],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0
    ) -> AsyncIterator[str]:
        """Generate a streaming response using Anthropic Claude"""
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages
        }

        if system:
            kwargs["system"] = system

        async with self.client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text


class OllamaProvider(LLMProvider):
    """Ollama local LLM provider"""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.1:8b"):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.client = httpx.AsyncClient(timeout=300.0)  # 5 min timeout for large models

    def _convert_messages(
        self,
        messages: list[Dict[str, str]],
        system: Optional[str] = None
    ) -> list[Dict[str, str]]:
        """Convert messages to Ollama format"""
        ollama_messages = []

        # Add system message if provided
        if system:
            ollama_messages.append({"role": "system", "content": system})

        # Convert messages
        for msg in messages:
            ollama_messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

        return ollama_messages

    async def generate_response(
        self,
        messages: list[Dict[str, str]],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0,
        stream: bool = False
    ) -> str:
        """Generate a response using Ollama"""
        if stream:
            return self.generate_stream(messages, system, max_tokens, temperature)

        ollama_messages = self._convert_messages(messages, system)

        payload = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }

        response = await self.client.post(
            f"{self.base_url}/api/chat",
            json=payload
        )
        response.raise_for_status()

        result = response.json()
        return result["message"]["content"]

    async def generate_stream(
        self,
        messages: list[Dict[str, str]],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0
    ) -> AsyncIterator[str]:
        """Generate a streaming response using Ollama"""
        ollama_messages = self._convert_messages(messages, system)

        payload = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }

        async with self.client.stream(
            "POST",
            f"{self.base_url}/api/chat",
            json=payload
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    import json
                    data = json.loads(line)
                    if "message" in data and "content" in data["message"]:
                        yield data["message"]["content"]

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


def get_llm_provider(
    provider: Optional[str] = None,
    anthropic_api_key: Optional[str] = None,
    ollama_base_url: Optional[str] = None,
    ollama_model: Optional[str] = None
) -> LLMProvider:
    """
    Factory function to get the appropriate LLM provider

    Args:
        provider: Either 'anthropic' or 'ollama'. If None, reads from LLM_PROVIDER env var
        anthropic_api_key: Anthropic API key. If None, reads from ANTHROPIC_API_KEY env var
        ollama_base_url: Ollama base URL. If None, reads from OLLAMA_BASE_URL env var
        ollama_model: Ollama model name. If None, reads from OLLAMA_MODEL env var

    Returns:
        LLMProvider instance

    Raises:
        ValueError: If provider is invalid or required credentials are missing
    """
    # Get provider from parameter or environment
    if provider is None:
        provider = os.getenv("LLM_PROVIDER", "anthropic").lower()

    if provider == "anthropic":
        # Get API key from parameter or environment
        api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "Anthropic API key is required. Set ANTHROPIC_API_KEY environment variable "
                "or pass anthropic_api_key parameter"
            )
        return AnthropicProvider(api_key=api_key)

    elif provider == "ollama":
        # Get Ollama configuration from parameters or environment
        base_url = ollama_base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        model = ollama_model or os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        return OllamaProvider(base_url=base_url, model=model)

    else:
        raise ValueError(
            f"Invalid LLM provider: {provider}. Must be 'anthropic' or 'ollama'"
        )
