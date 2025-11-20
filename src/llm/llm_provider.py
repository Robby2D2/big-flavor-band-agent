"""
LLM Provider Abstraction Layer
Supports both Anthropic Claude and local Ollama models with tool calling
"""
import os
import json
from typing import Optional, AsyncIterator, Dict, Any, List
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

    @abstractmethod
    def supports_tool_calling(self) -> bool:
        """Check if this provider supports tool calling"""
        pass

    @abstractmethod
    async def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0
    ) -> Dict[str, Any]:
        """
        Generate a response with tool calling support.

        Args:
            messages: Conversation messages
            tools: Tool definitions (Anthropic format for compatibility)
            system: System prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Returns:
            Dict containing:
                - content: List of content blocks (text and/or tool_use)
                - stop_reason: Why generation stopped
                - usage: Token usage info
        """
        pass


def convert_anthropic_tools_to_ollama(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert Anthropic tool format to Ollama tool format.

    Anthropic format:
    {
        "name": "tool_name",
        "description": "description",
        "input_schema": {
            "type": "object",
            "properties": {...},
            "required": [...]
        }
    }

    Ollama format:
    {
        "type": "function",
        "function": {
            "name": "tool_name",
            "description": "description",
            "parameters": {
                "type": "object",
                "properties": {...},
                "required": [...]
            }
        }
    }
    """
    ollama_tools = []
    for tool in tools:
        ollama_tool = {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"]
            }
        }
        ollama_tools.append(ollama_tool)
    return ollama_tools


def convert_ollama_tool_calls_to_anthropic(tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert Ollama tool calls to Anthropic format.

    Ollama format:
    {
        "function": {
            "name": "tool_name",
            "arguments": {...}
        }
    }

    Anthropic format:
    {
        "type": "tool_use",
        "id": "unique_id",
        "name": "tool_name",
        "input": {...}
    }
    """
    anthropic_blocks = []
    for i, call in enumerate(tool_calls):
        func = call.get("function", {})

        # Parse arguments if they're a string
        arguments = func.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}

        block = {
            "type": "tool_use",
            "id": f"toolu_{i}_{func.get('name', 'unknown')}",
            "name": func.get("name", ""),
            "input": arguments
        }
        anthropic_blocks.append(block)
    return anthropic_blocks


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

    def supports_tool_calling(self) -> bool:
        """Anthropic Claude supports tool calling"""
        return True

    async def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0
    ) -> Dict[str, Any]:
        """Generate a response with tool calling using Anthropic Claude"""
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
            "tools": tools  # Anthropic format directly
        }

        if system:
            kwargs["system"] = system

        response = await self.client.messages.create(**kwargs)

        return {
            "content": response.content,
            "stop_reason": response.stop_reason,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens
            }
        }


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

    def supports_tool_calling(self) -> bool:
        """Ollama supports tool calling for compatible models"""
        return True

    async def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0
    ) -> Dict[str, Any]:
        """
        Generate a response with tool calling using Ollama.
        Converts Anthropic tool format to Ollama format internally.
        """
        # Convert tools from Anthropic format to Ollama format
        ollama_tools = convert_anthropic_tools_to_ollama(tools)

        # Convert messages to Ollama format
        ollama_messages = self._convert_messages(messages, system)

        payload = {
            "model": self.model,
            "messages": ollama_messages,
            "tools": ollama_tools,
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
        message = result.get("message", {})

        # Build response in Anthropic-compatible format
        content_blocks = []

        # Add text content if present
        text_content = message.get("content", "")
        if text_content and text_content.strip():
            content_blocks.append({
                "type": "text",
                "text": text_content
            })

        # Add tool calls if present
        tool_calls = message.get("tool_calls", [])
        if tool_calls:
            # Convert Ollama tool calls to Anthropic format
            anthropic_tool_blocks = convert_ollama_tool_calls_to_anthropic(tool_calls)
            content_blocks.extend(anthropic_tool_blocks)

        # Determine stop reason
        stop_reason = "end_turn"
        if tool_calls:
            stop_reason = "tool_use"

        # Token usage (Ollama doesn't provide this, so estimate)
        # We'll use rough estimates based on response length
        prompt_eval_count = result.get("prompt_eval_count", 0)
        eval_count = result.get("eval_count", 0)

        return {
            "content": content_blocks,
            "stop_reason": stop_reason,
            "usage": {
                "input_tokens": prompt_eval_count if prompt_eval_count > 0 else 0,
                "output_tokens": eval_count if eval_count > 0 else 0
            }
        }


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
