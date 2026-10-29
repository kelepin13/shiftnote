from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_MODELS = {
    # Small, fast models are enough for extraction. Override with SHIFTNOTE_MODEL; check your
    # provider's model list, since names change over time.
    "openai": "gpt-5-mini",
    "anthropic": "claude-haiku-5-5",
    "gemini": "gemini-2.5-flash",
    "mock": "rules-v1",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SHIFTNOTE_", env_file=".env", extra="ignore")

    provider: Literal["mock", "openai", "anthropic", "gemini"] = "mock"
    model: str | None = None
    api_key: str = ""
    base_url: str | None = None  # e.g. an OpenAI-compatible server or a proxy
    timeout_s: float = 20.0
    max_attempts: int = 2  # first try + repairs

    @property
    def resolved_model(self) -> str:
        return self.model or DEFAULT_MODELS[self.provider]
