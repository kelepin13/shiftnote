"""The HTTP adapters, against recorded response shapes (no network, no API key)."""

import asyncio
import json

import httpx
import pytest
import respx

from shiftnote.providers import ProviderError
from shiftnote.providers.http_providers import AnthropicProvider, GeminiProvider, OpenAIProvider

ANSWER = {"patient": {"reference": "room 1"}, "vitals": []}
MESSAGES = [{"role": "user", "content": "note"}]


def call(provider):
    return asyncio.run(provider.complete_json("system", MESSAGES, {"type": "object"}))


@respx.mock
def test_openai_reads_json_content_and_sends_schema():
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(ANSWER)}}]})
    )
    assert call(OpenAIProvider("key", "m", 5)) == ANSWER
    sent = json.loads(route.calls[0].request.content)
    assert sent["response_format"]["type"] == "json_schema"
    assert route.calls[0].request.headers["authorization"] == "Bearer key"


@respx.mock
def test_anthropic_reads_forced_tool_call():
    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200, json={"content": [{"type": "tool_use", "name": "record_care_note", "input": ANSWER}]}
        )
    )
    assert call(AnthropicProvider("key", "m", 5)) == ANSWER
    sent = json.loads(route.calls[0].request.content)
    assert sent["tool_choice"] == {"type": "tool", "name": "record_care_note"}


@respx.mock
def test_gemini_reads_json_text_even_in_a_code_fence():
    fenced = "```json\n" + json.dumps(ANSWER) + "\n```"
    respx.post("https://generativelanguage.googleapis.com/v1beta/models/m:generateContent").mock(
        return_value=httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": fenced}]}}]})
    )
    assert call(GeminiProvider("key", "m", 5)) == ANSWER


@respx.mock
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(429, json={"error": "rate limited"}),
        httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]}),
        httpx.Response(200, json={"unexpected": True}),
    ],
)
def test_openai_failures_become_provider_errors(response):
    respx.post("https://api.openai.com/v1/chat/completions").mock(return_value=response)
    with pytest.raises(ProviderError):
        call(OpenAIProvider("key", "m", 5))


@respx.mock
def test_timeout_becomes_provider_error():
    respx.post("https://api.anthropic.com/v1/messages").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(ProviderError, match="timed out"):
        call(AnthropicProvider("key", "m", 5))


def test_missing_api_key_is_rejected_at_startup():
    with pytest.raises(ValueError, match="missing API key"):
        OpenAIProvider("", "m", 5)
