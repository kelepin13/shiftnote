from shiftnote.models import CareNote, Severity
from shiftnote.validate import is_grounded, number_in, validate

from .conftest import NOTE, good_answer


def errors(note_dict, text=NOTE):
    return [i for i in validate(CareNote.model_validate(note_dict), text) if i.severity is Severity.error]


def test_grounding_ignores_case_whitespace_and_decimal_commas():
    assert is_grounded("temp 38.2", "Temp   38,2 C at 06:00")
    assert not is_grounded("temp 39.2", "Temp 38,2 C")


def test_number_must_appear_in_its_evidence():
    assert number_in(38.2, "Temp 38,2 C")
    assert not number_in(39, "Temp 38,2 C")


def test_good_answer_passes():
    assert errors(good_answer()) == []


def test_invented_evidence_is_an_error():
    data = good_answer()
    data["medications"][0]["evidence"] = "Ibuprofen 400 mg given"
    [issue] = errors(data)
    assert issue.path == "medications[0]" and "does not appear" in issue.message


def test_value_not_in_evidence_is_an_error():
    data = good_answer()
    data["vitals"][1]["value"] = 29  # model swapped a number
    assert any("not in its evidence" in i.message for i in errors(data))


def test_blood_pressure_rules():
    data = good_answer()
    data["vitals"][0]["value2"] = None
    assert any("diastolic" in i.message for i in errors(data))
    data["vitals"][0].update(value=85, value2=145, evidence="BP 145/85")
    assert any("lower than systolic" in i.message for i in errors(data))


def test_impossible_value_is_error_and_unusual_value_is_warning():
    text = "HR 300. SpO2 86%."
    data = {
        "patient": {},
        "vitals": [
            {"type": "heart_rate", "value": 300, "unit": "bpm", "evidence": "HR 300"},
            {"type": "spo2", "value": 86, "unit": "%", "evidence": "SpO2 86%"},
        ],
    }
    issues = validate(CareNote.model_validate(data), text)
    assert [(i.path, i.severity) for i in issues] == [("vitals[0]", Severity.error), ("vitals[1]", Severity.warning)]


def test_time_must_be_hh_mm():
    data = good_answer()
    data["tasks"][0]["due"] = "10am"
    assert any("HH:MM" in i.message for i in errors(data))
