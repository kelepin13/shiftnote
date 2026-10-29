"""Checks the model's output against the original note and against clinical common sense.

Two kinds of problems:
- errors: the item is wrong or invented (evidence not in the note, number not in its evidence,
  impossible value). Errors trigger a repair attempt; if they survive, the item is dropped.
- warnings: plausible but unusual (e.g. SpO2 of 86%). The item stays; the note needs review.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .models import CareNote, Issue, Severity, VitalType

# (hard_min, hard_max, normal_min, normal_max). Outside hard: impossible -> error.
# Outside normal: possible but clinically notable -> warning.
RANGES: dict[VitalType, tuple[float, float, float, float]] = {
    VitalType.heart_rate: (20, 250, 50, 120),
    VitalType.temperature: (30, 43, 35.5, 38.0),
    VitalType.spo2: (50, 100, 92, 100),
    VitalType.respiratory_rate: (4, 60, 10, 24),
    VitalType.pain_score: (0, 10, 0, 6),
}
SYSTOLIC = (50, 260, 90, 160)
DIASTOLIC = (20, 160, 50, 100)
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def normalize(text: str) -> str:
    """Lowercase, unify unicode, collapse whitespace and treat ',' decimals like '.'."""
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"(\d),(\d)", r"\1.\2", text)
    return re.sub(r"\s+", " ", text).strip(" .;:,")


def is_grounded(evidence: str, note: str) -> bool:
    ev = normalize(evidence)
    return bool(ev) and ev in normalize(note)


def number_in(value: float, evidence: str) -> bool:
    """Does the evidence actually contain this number? Catches swapped or invented values."""
    numbers = {float(n) for n in re.findall(r"\d+(?:\.\d+)?", normalize(evidence))}
    return value in numbers


@dataclass
class _Check:
    issues: list[Issue]

    def error(self, path: str, message: str) -> None:
        self.issues.append(Issue(path=path, severity=Severity.error, message=message))

    def warn(self, path: str, message: str) -> None:
        self.issues.append(Issue(path=path, severity=Severity.warning, message=message))


def _range(c: _Check, path: str, label: str, value: float, bounds: tuple[float, float, float, float]) -> None:
    hard_min, hard_max, normal_min, normal_max = bounds
    if not hard_min <= value <= hard_max:
        c.error(path, f"{label} {value:g} is not physiologically possible")
    elif not normal_min <= value <= normal_max:
        c.warn(path, f"{label} {value:g} is outside the usual range; confirm it")


def validate(note: CareNote, text: str) -> list[Issue]:
    c = _Check([])

    if note.patient.evidence and not is_grounded(note.patient.evidence, text):
        c.error("patient", f"evidence {note.patient.evidence!r} does not appear in the note")

    groups = {
        "vitals": note.vitals,
        "medications": note.medications,
        "observations": note.observations,
        "tasks": note.tasks,
        "risk_flags": note.risk_flags,
    }
    for name, items in groups.items():
        for i, item in enumerate(items):
            if not is_grounded(item.evidence, text):
                c.error(f"{name}[{i}]", f"evidence {item.evidence!r} does not appear in the note")
            time = getattr(item, "time", None) or getattr(item, "due", None)
            if time is not None and not TIME_RE.match(time):
                c.error(f"{name}[{i}]", f"time {time!r} is not HH:MM")

    for i, v in enumerate(note.vitals):
        path = f"vitals[{i}]"
        if not number_in(v.value, v.evidence):
            c.error(path, f"value {v.value:g} is not in its evidence {v.evidence!r}")
        if v.type is VitalType.blood_pressure:
            if v.value2 is None:
                c.error(path, "blood pressure needs a diastolic value (value2)")
                continue
            if not number_in(v.value2, v.evidence):
                c.error(path, f"diastolic {v.value2:g} is not in its evidence {v.evidence!r}")
            if v.value2 >= v.value:
                c.error(path, "diastolic must be lower than systolic")
            _range(c, path, "Systolic", v.value, SYSTOLIC)
            _range(c, path, "Diastolic", v.value2, DIASTOLIC)
        elif v.type is VitalType.temperature and v.value > 50:
            c.warn(path, f"temperature {v.value:g} looks like °F; documented as written")
        elif v.type in RANGES:
            _range(c, path, v.type.value.replace("_", " ").capitalize(), v.value, RANGES[v.type])

    return c.issues


def error_messages(issues: list[Issue]) -> list[str]:
    return [f"{i.path}: {i.message}" for i in issues if i.severity is Severity.error]
