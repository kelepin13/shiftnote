"""Offline stand-in for an LLM, so the app runs, demos and tests without an API key.

It is deliberately simple (rules, not a model) and says so in its name and in every response.
"""

from __future__ import annotations

import re
from typing import Any

from ..fallback import extract_rule_based
from .base import Message

# A task sentence runs until ". ", ";" or a newline; a "." inside a number (38.5) does not end it.
TASK_HINTS = re.compile(
    r"(?:^|[.;\n]\s*)((?:please|pls|bitte|tolong|recheck|re-check|check|kontrol|cek)\b(?:[^.;\n]|\.(?=\d))*)",
    re.IGNORECASE,
)
URGENT = re.compile(r"\b(?:asap|urgent|immediately|sofort|segera|stat)\b", re.IGNORECASE)
TIME = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")


class MockProvider:
    name = "mock"
    model = "rules-v1"

    async def complete_json(self, system: str, messages: list[Message], schema: dict[str, Any]) -> dict[str, Any]:
        note_text = messages[0]["content"].split("<<<", 1)[-1].rsplit(">>>", 1)[0].strip()
        note = extract_rule_based(note_text).model_dump(mode="json")
        note["uncertainties"] = ["Structured by the offline mock (rules, not an LLM). Set SHIFTNOTE_PROVIDER for AI."]
        for m in TASK_HINTS.finditer(note_text):
            sentence = m[1].strip()
            due = TIME.search(sentence)
            note["tasks"].append(
                {
                    "description": sentence[:1].upper() + sentence[1:],
                    "due": f"{int(due[1]):02d}:{due[2]}" if due else None,
                    "priority": "urgent" if URGENT.search(sentence) else "soon",
                    "evidence": sentence,
                }
            )
        return note
