"""Rule-based extraction used when the LLM is down, times out, or keeps producing invalid output.

It only finds the things regexes find reliably (vitals and the patient's room), so its result is
always marked `partial`: the original note is never lost and the nurse knows to review it.
Labels cover English, German and Indonesian handover shorthand.
"""

from __future__ import annotations

import re

from .models import CareNote, Patient, Vital, VitalType

FLAGS = re.IGNORECASE
NUM = r"(\d{1,3}(?:[.,]\d)?)"

PATTERNS: list[tuple[VitalType, str, re.Pattern[str]]] = [
    (
        VitalType.blood_pressure,
        "mmHg",
        re.compile(r"\b(?:BP|RR|TD|tensi|tekanan darah|blood pressure)\s*[:=]?\s*(\d{2,3})\s*/\s*(\d{2,3})", FLAGS),
    ),
    (
        VitalType.heart_rate,
        "bpm",
        re.compile(r"\b(?:HR|pulse|puls|nadi|HF|heart rate|herzfrequenz)\s*[:=]?\s*(\d{2,3})\b", FLAGS),
    ),
    (
        VitalType.temperature,
        "°C",
        re.compile(r"\b(?:temp(?:erature)?|temperatur|suhu|T)\s*[:=]?\s*(\d{2}(?:[.,]\d)?)\s*°?\s*C?\b", FLAGS),
    ),
    (
        VitalType.spo2,
        "%",
        re.compile(r"(?:SpO2|SpO₂|O2 ?sat|sats?|sättigung|saturasi)\s*[:=]?\s*(\d{2,3})\s*%?", FLAGS),
    ),
    (
        VitalType.respiratory_rate,
        "/min",
        re.compile(r"\b(?:resp(?:iratory)? rate|RR|AF|atemfrequenz|napas)\s*[:=]?\s*(\d{1,2})\b(?!\s*/)", FLAGS),
    ),
    (
        VitalType.blood_glucose,
        "mmol/L",
        re.compile(
            r"\b(?:BZ|BG|BSL|glucose|blutzucker|gula darah|GDS)\s*[:=]?\s*" + NUM + r"\s*(mmol/l|mg/dl)?", FLAGS
        ),
    ),
    (
        VitalType.pain_score,
        "/10",
        re.compile(r"\b(?:pain(?: score)?|schmerz(?:en)?|nyeri|NRS|VAS)\s*[:=]?\s*(\d{1,2})\s*/\s*10", FLAGS),
    ),
]

ROOM = re.compile(r"\b(?:room|rm\.?|zimmer|zi\.?|kamar)\s*(\d+[a-z]?)(?:\s*,?\s*(?:bed|bett)\s*([a-z0-9]+))?", FLAGS)


def _num(text: str) -> float:
    return float(text.replace(",", "."))


def extract_rule_based(text: str) -> CareNote:
    vitals: list[Vital] = []
    taken: list[tuple[int, int]] = []  # spans already used, so "RR 130/80" is not also read as a resp. rate

    for vital_type, unit, pattern in PATTERNS:
        for m in pattern.finditer(text):
            if any(start < m.end() and m.start() < end for start, end in taken):
                continue
            taken.append(m.span())
            if vital_type is VitalType.blood_pressure:
                vitals.append(
                    Vital(type=vital_type, value=_num(m[1]), value2=_num(m[2]), unit=unit, evidence=m[0].strip())
                )
            else:
                chosen_unit = unit
                if vital_type is VitalType.blood_glucose and m.lastindex and m.lastindex >= 2 and m[2]:
                    chosen_unit = "mg/dL" if m[2].lower() == "mg/dl" else "mmol/L"
                vitals.append(Vital(type=vital_type, value=_num(m[1]), unit=chosen_unit, evidence=m[0].strip()))

    patient = Patient()
    if room := ROOM.search(text):
        reference = f"room {room[1]}" + (f" bed {room[2]}" if room[2] else "")
        patient = Patient(reference=reference, evidence=room[0].strip())

    return CareNote(
        patient=patient,
        vitals=vitals,
        uncertainties=["Automatic structuring was unavailable; only vital signs were extracted. Read the full note."],
    )
