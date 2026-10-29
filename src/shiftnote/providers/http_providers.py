"""OpenAI, Anthropic and Gemini over plain HTTP.

Plain `httpx` instead of three vendor SDKs: one dependency, one timeout and error policy, and
each adapter is ~30 lines that are easy to read and to mock in tests.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from .base import Message, ProviderError


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):  # some models wrap JSON in a code fence
        text = text.strip("`").removeprefix("json").strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as e:
        raise ProviderError(f"model returned invalid JSON: {e}") from e
    if not isinstance(value, dict):
        raise ProviderError("model returned JSON that is not an object")
    return value


class _HttpProvider:
    name = "base"

    def __init__(self, api_key: str, model: str, timeout_s: float, base_url: str | None = None):
        if not api_key:
            raise ValueError(f"{self.name}: missing API key")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = httpx.Timeout(timeout_s, connect=5.0)

    async def _post(self, url: str, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=body, headers=headers)
        except httpx.TimeoutException as e:
            raise ProviderError(f"{self.name}: request timed out") from e
        except httpx.HTTPError as e:
            raise ProviderError(f"{self.name}: network error: {e}") from e
        if response.status_code >= 400:
            # Body may echo the prompt; keep only the start of it, and never log the note itself.
            raise ProviderError(f"{self.name}: HTTP {response.status_code}: {response.text[:200]}")
        return response.json()


class OpenAIProvider(_HttpProvider):
    """Chat Completions with a JSON-schema response format. Also works with OpenAI-compatible servers."""

    name = "openai"

    async def complete_json(self, system: str, messages: list[Message], schema: dict[str, Any]) -> dict[str, Any]:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "care_note", "schema": schema, "strict": False},
            },
        }
        data = await self._post(
            f"{self.base_url or 'https://api.openai.com'}/v1/chat/completions",
            body,
            {"Authorization": f"Bearer {self.api_key}"},
        )
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderError("openai: unexpected response shape") from e
        return _parse_json(content or "")


class AnthropicProvider(_HttpProvider):
    """Messages API, forcing a single tool call whose input is the structured note."""

    name = "anthropic"

    async def complete_json(self, system: str, messages: list[Message], schema: dict[str, Any]) -> dict[str, Any]:
        body = {
            "model": self.model,
            "max_tokens": 4096,
            "system": system,
            "messages": messages,
            "tools": [
                {"name": "record_care_note", "description": "Record the structured note.", "input_schema": schema}
            ],
            "tool_choice": {"type": "tool", "name": "record_care_note"},
        }
        data = await self._post(
            f"{self.base_url or 'https://api.anthropic.com'}/v1/messages",
            body,
            {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
        )
        for block in data.get("content", []):
            if block.get("type") == "tool_use" and isinstance(block.get("input"), dict):
                return block["input"]
        raise ProviderError("anthropic: no tool call in response")


class GeminiProvider(_HttpProvider):
    """generateContent in JSON mode; the schema is given in the prompt for broad model support."""

    name = "gemini"

    async def complete_json(self, system: str, messages: list[Message], schema: dict[str, Any]) -> dict[str, Any]:
        contents = [
            {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
            for m in messages
        ]
        body = {
            "systemInstruction": {
                "parts": [{"text": f"{system}\n\nReturn JSON matching this schema:\n{json.dumps(schema)}"}]
            },
            "contents": contents,
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
        }
        base = self.base_url or "https://generativelanguage.googleapis.com"
        data = await self._post(
            f"{base}/v1beta/models/{self.model}:generateContent", body, {"x-goog-api-key": self.api_key}
        )
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderError("gemini: unexpected response shape") from e
        return _parse_json(text)
