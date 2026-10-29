from __future__ import annotations

from typing import Any, Protocol

Message = dict[str, str]  # {"role": "user" | "assistant", "content": "..."}


class ProviderError(Exception):
    """The provider could not produce an answer (network, timeout, auth, rate limit, bad reply)."""


class LLMProvider(Protocol):
    name: str
    model: str

    async def complete_json(self, system: str, messages: list[Message], schema: dict[str, Any]) -> dict[str, Any]:
        """Return one JSON object that should match `schema`. Raise ProviderError on failure."""
        ...
