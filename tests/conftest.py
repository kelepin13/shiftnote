from __future__ import annotations

from typing import Any

import pytest

from shiftnote.providers import ProviderError

NOTE = (
    "Room 12 bed B. BP 145/85, HR 92, temp 38.2 C at 06:00, SpO2 94%. "
    "Paracetamol 1 g oral given 05:30. Please recheck temp at 10:00."
)


def good_answer() -> dict[str, Any]:
    return {
        "patient": {"reference": "room 12 bed B", "evidence": "Room 12 bed B"},
        "vitals": [
            {"type": "blood_pressure", "value": 145, "value2": 85, "unit": "mmHg", "evidence": "BP 145/85"},
            {"type": "heart_rate", "value": 92, "unit": "bpm", "evidence": "HR 92"},
            {"type": "spo2", "value": 94, "unit": "%", "evidence": "SpO2 94%"},
        ],
        "medications": [
            {
                "name": "Paracetamol",
                "dose": "1 g",
                "route": "oral",
                "status": "given",
                "time": "05:30",
                "evidence": "Paracetamol 1 g oral given 05:30",
            }
        ],
        "tasks": [
            {
                "description": "Recheck temperature",
                "due": "10:00",
                "priority": "soon",
                "evidence": "Please recheck temp at 10:00",
            }
        ],
    }


class ScriptedProvider:
    """Returns the given answers in order (dicts, or exceptions to raise) and records what it was asked."""

    name = "scripted"
    model = "test"

    def __init__(self, *answers: Any):
        self.answers = list(answers)
        self.calls: list[list[dict[str, str]]] = []

    async def complete_json(self, system, messages, schema):
        self.calls.append(list(messages))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def note() -> str:
    return NOTE


@pytest.fixture
def down() -> ProviderError:
    return ProviderError("scripted: request timed out")
