"""Abstract base class for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Any, Optional


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, api_key: str, **kwargs):
        """Initialize the provider with API key and optional parameters.

        Args:
            api_key: The API key for the provider
            **kwargs: Additional provider-specific configuration
        """
        self.api_key = api_key
        self.config = kwargs

    @abstractmethod
    async def generate_completion(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ) -> str:
        """Generate a completion from the LLM.

        Args:
            prompt: The user prompt
            system_prompt: System prompt to guide behavior
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific parameters

        Returns:
            Generated text response
        """
        pass

    @abstractmethod
    async def generate_completion_stream(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ) -> AsyncIterator[str]:
        """Generate a streaming completion from the LLM.

        Args:
            prompt: The user prompt
            system_prompt: System prompt to guide behavior
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific parameters

        Yields:
            Generated text chunks
        """
        pass

    @abstractmethod
    def validate_api_key(self, api_key: str) -> bool:
        """Validate the API key format.

        Args:
            api_key: The API key to validate

        Returns:
            True if the API key appears valid, False otherwise
        """
        pass

    def get_provider_name(self) -> str:
        """Get the provider name.

        Returns:
            Provider identifier string
        """
        return self.__class__.__name__.replace("Adapter", "").lower()