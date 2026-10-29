from __future__ import annotations

from ..config import Settings
from .base import LLMProvider, Message, ProviderError
from .http_providers import AnthropicProvider, GeminiProvider, OpenAIProvider
from .mock import MockProvider

__all__ = ["LLMProvider", "Message", "ProviderError", "MockProvider", "build_provider"]


def build_provider(settings: Settings) -> LLMProvider:
    if settings.provider == "mock":
        return MockProvider()
    cls = {"openai": OpenAIProvider, "anthropic": AnthropicProvider, "gemini": GeminiProvider}[settings.provider]
    return cls(settings.api_key, settings.resolved_model, settings.timeout_s, settings.base_url)
