import asyncio

from shiftnote.evals import DEFAULT_CASES, load_cases, run_evals, score_case, summarize
from shiftnote.models import CareNote, Status, StructureResult
from shiftnote.providers import MockProvider


def result_with(note: dict) -> StructureResult:
    return StructureResult(
        status=Status.complete,
        note=CareNote.model_validate(note),
        issues=[],
        source="llm",
        provider="t",
        model="t",
        attempts=1,
        latency_ms=5,
    )


CASE = {
    "id": "c",
    "text": "unused",
    "expected": {
        "vitals": [{"type": "blood_pressure", "value": 145, "value2": 85}, {"type": "heart_rate", "value": 92}],
        "medications": [{"name": "insulin", "status": "held"}],
        "tasks": [{"keyword": "glucose", "due": "11:30"}],
        "risk_flags": ["fall"],
    },
}


def test_scores_hits_misses_and_wrong_status():
    score = score_case(
        CASE,
        result_with(
            {
                "patient": {},
                "vitals": [
                    {"type": "blood_pressure", "value": 145, "value2": 85, "unit": "mmHg", "evidence": "x"},
                    {"type": "heart_rate", "value": 29, "unit": "bpm", "evidence": "x"},
                ],
                "medications": [{"name": "Insulin glargine", "status": "given", "evidence": "x"}],
                "tasks": [{"description": "Check blood glucose", "due": "11:30", "priority": "soon", "evidence": "x"}],
                "risk_flags": [{"type": "allergy", "detail": "x", "evidence": "x"}],
            }
        ),
    )
    assert (score.vitals.hit, score.vitals.predicted, score.vitals.expected) == (1, 2, 2)
    assert score.meds.hit == 1 and score.med_status_right == 0
    assert score.tasks.hit == 1
    assert score.risks.hit == 0 and score.risks.predicted == 1
    assert any("status given, expected held" in n for n in score.notes)


def test_every_case_file_runs_end_to_end_with_the_mock():
    cases = load_cases(DEFAULT_CASES)
    assert len(cases) >= 8
    summary = summarize(asyncio.run(run_evals(MockProvider(), cases)))
    assert summary["cases"] == len(cases)
    assert summary["vitals_recall"] > 0.8  # the rules alone find most vitals
    assert summary["meds_recall"] == 0  # ...and nothing else: that is what the LLM is for
