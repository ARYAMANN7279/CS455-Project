"""Concrete implementations of LLM providers."""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator, Dict, Any, Optional

import httpx

from .provider import LLMProvider

log = logging.getLogger(__name__)


class MistralAdapter(LLMProvider):
    """Mistral AI adapter."""

    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key, **kwargs)
        self.base_url = "https://api.mistral.ai/v1"
        self.model = kwargs.get("model", "mistral-tiny")

    async def generate_completion(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ) -> str:
        """Generate a completion using Mistral AI."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        **kwargs
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                result = response.json()
                return result["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as e:
                log.error(f"Mistral API error: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                log.error(f"Error calling Mistral API: {e}")
                raise

    async def generate_completion_stream(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ) -> AsyncIterator[str]:
        """Generate a streaming completion using Mistral AI."""
        async with httpx.AsyncClient() as client:
            try:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "stream": True,
                        **kwargs
                    },
                    timeout=30.0
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data = line[6:]  # Remove "data: " prefix
                            if data.strip() == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                                if chunk["choices"][0]["delta"].get("content"):
                                    yield chunk["choices"][0]["delta"]["content"]
                            except (json.JSONDecodeError, KeyError, IndexError):
                                # Skip malformed chunks
                                continue
            except httpx.HTTPStatusError as e:
                log.error(f"Mistral API error: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                log.error(f"Error calling Mistral API: {e}")
                raise

    def validate_api_key(self, api_key: str) -> bool:
        """Validate Mistral API key format.

        Mistral API keys typically start with something like 'sk-' or similar.
        For now, we'll do basic validation.
        """
        return bool(api_key and len(api_key) >= 10)


class HuggingFaceAdapter(LLMProvider):
    """Hugging Face Inference API adapter for free models."""

    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key, **kwargs)
        self.base_url = "https://api-inference.huggingface.co/models"
        self.model = kwargs.get("model", "HuggingFaceH4/zephyr-7b-beta")

    async def generate_completion(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ) -> str:
        """Generate a completion using Hugging Face Inference API."""
        # Combine system and user prompts for HF format
        full_prompt = f"<|system|>\n{system_prompt}</s>\n<|user|>\n{prompt}</s>\n<|assistant|>\n"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/{self.model}",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "inputs": full_prompt,
                        "parameters": {
                            "temperature": temperature,
                            "max_new_tokens": max_tokens,
                            "return_full_text": False,
                            **kwargs
                        }
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                result = response.json()
                # HF returns a list of generated texts
                if isinstance(result, list) and len(result) > 0:
                    return result[0].get("generated_text", "")
                return str(result)
            except httpx.HTTPStatusError as e:
                log.error(f"Hugging Face API error: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                log.error(f"Error calling Hugging Face API: {e}")
                raise

    async def generate_completion_stream(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ) -> AsyncIterator[str]:
        """Generate a streaming completion using Hugging Face.

        Note: Hugging Face Inference API doesn't consistently support streaming
        for all models, so we'll simulate it by yielding the complete response.
        """
        response = await self.generate_completion(
            prompt, system_prompt, temperature, max_tokens, **kwargs
        )
        # Simulate streaming by yielding chunks of the response
        words = response.split()
        for i in range(0, len(words), 5):  # Yield 5 words at a time
            chunk = " ".join(words[i:i+5])
            if i + 5 < len(words):
                chunk += " "
            yield chunk

    def validate_api_key(self, api_key: str) -> bool:
        """Validate Hugging Face API key format.

        HF tokens typically start with 'hf_'.
        """
        return bool(api_key and api_key.startswith("hf_") and len(api_key) >= 10)