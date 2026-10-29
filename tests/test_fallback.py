from shiftnote.fallback import extract_rule_based
from shiftnote.models import VitalType


def vitals(text):
    return {(v.type, v.value, v.value2) for v in extract_rule_based(text).vitals}


def test_english_shorthand():
    assert vitals("BP 145/85, HR 92, temp 38.2 C, SpO2 94%, RR 18") == {
        (VitalType.blood_pressure, 145, 85),
        (VitalType.heart_rate, 92, None),
        (VitalType.temperature, 38.2, None),
        (VitalType.spo2, 94, None),
        (VitalType.respiratory_rate, 18, None),
    }


def test_german_rr_with_slash_is_blood_pressure_not_respiratory_rate():
    found = vitals("RR 160/95, Puls 88, Temp 37,4, Atemfrequenz 24, BZ 11,2 mmol/l")
    assert (VitalType.blood_pressure, 160, 95) in found
    assert (VitalType.respiratory_rate, 24, None) in found
    assert (VitalType.temperature, 37.4, None) in found
    assert (VitalType.blood_glucose, 11.2, None) in found
    assert not any(t is VitalType.respiratory_rate and v == 160 for t, v, _ in found)


def test_indonesian_labels_and_room():
    note = extract_rule_based("Kamar 7. Tensi 90/60, nadi 112, suhu 36,8, saturasi 91%.")
    assert note.patient.reference == "room 7"
    assert {v.type for v in note.vitals} == {
        VitalType.blood_pressure,
        VitalType.heart_rate,
        VitalType.temperature,
        VitalType.spo2,
    }


def test_evidence_is_copied_from_the_note():
    text = "Zimmer 4 Bett 2: RR 160/95"
    note = extract_rule_based(text)
    assert all(v.evidence in text for v in note.vitals)
    assert note.patient.reference == "room 4 bed 2"
