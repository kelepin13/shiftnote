"""HTTP API and the demo page.

uvicorn shiftnote.api:app --reload
"""

from __future__ import annotations

import logging
from functools import cache
from importlib.resources import files
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.responses import HTMLResponse

from .config import Settings
from .models import StructureRequest, StructureResult
from .pipeline import structure_note
from .providers import LLMProvider, build_provider

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="Shiftnote",
    version="1.0.0",
    description="Turns a nurse's handover note into validated, structured care documentation.",
)


@cache
def get_settings() -> Settings:
    return Settings()


@cache
def get_provider() -> LLMProvider:
    return build_provider(get_settings())


ProviderDep = Annotated[LLMProvider, Depends(get_provider)]


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def demo_page() -> str:
    return files("shiftnote").joinpath("static/index.html").read_text(encoding="utf-8")


@app.get("/health")
def health(provider: ProviderDep) -> dict[str, str]:
    return {"status": "ok", "provider": provider.name, "model": provider.model}


@app.post("/v1/notes/structure", response_model=StructureResult)
async def structure(body: StructureRequest, provider: ProviderDep) -> StructureResult:
    """Structure one handover note. Always answers: when the LLM fails, the result is `partial`."""
    return await structure_note(body.text, provider, max_attempts=get_settings().max_attempts)
