import asyncio
import copy

from shiftnote.models import Status
from shiftnote.pipeline import structure_note

from .conftest import ScriptedProvider, good_answer


def run(note, provider, attempts=2):
    return asyncio.run(structure_note(note, provider, max_attempts=attempts))


def test_valid_answer_is_complete_on_first_attempt(note):
    result = run(note, ScriptedProvider(good_answer()))
    assert result.status is Status.complete
    assert result.attempts == 1 and result.source == "llm"
    assert len(result.note.vitals) == 3


def test_invented_item_is_sent_back_and_repaired(note):
    bad = good_answer()
    bad["medications"].append({"name": "Ibuprofen", "status": "given", "evidence": "Ibuprofen 400 mg given"})
    provider = ScriptedProvider(bad, good_answer())

    result = run(note, provider)

    assert result.status is Status.complete and result.attempts == 2
    repair_request = provider.calls[1][-1]["content"]
    assert "medications[1]" in repair_request and "does not appear in the note" in repair_request


def test_item_still_invented_after_repairs_is_removed_and_reported(note):
    bad = good_answer()
    bad["medications"].append({"name": "Ibuprofen", "status": "given", "evidence": "Ibuprofen 400 mg given"})
    result = run(note, ScriptedProvider(bad, copy.deepcopy(bad)))

    assert result.status is Status.needs_review
    assert [m.name for m in result.note.medications] == ["Paracetamol"]
    assert any(i.message.startswith("Removed:") and i.path == "medications[1]" for i in result.issues)


def test_schema_invalid_answers_fall_back_to_rules(note):
    result = run(note, ScriptedProvider({"vitals": "lots"}, {"patient": 3}))
    assert result.status is Status.partial and result.source == "fallback"
    assert {v.type.value for v in result.note.vitals} >= {"blood_pressure", "heart_rate", "spo2"}


def test_provider_outage_falls_back_without_losing_the_note(note, down):
    result = run(note, ScriptedProvider(down))
    assert result.status is Status.partial and result.source == "fallback"
    assert result.note.uncertainties  # tells the nurse to read the full note


def test_unusual_value_means_review(note):
    answer = good_answer()
    answer["vitals"].append(
        {"type": "temperature", "value": 38.2, "unit": "°C", "time": "06:00", "evidence": "temp 38.2 C at 06:00"}
    )
    result = run(note, ScriptedProvider(answer))
    assert result.status is Status.needs_review
    assert any(i.path == "vitals[3]" and i.severity.value == "warning" for i in result.issues)


def test_model_uncertainty_means_review(note):
    answer = good_answer() | {"uncertainties": ["Dose of evening insulin unclear"]}
    assert run(note, ScriptedProvider(answer)).status is Status.needs_review
