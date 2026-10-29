"""The structured care note the LLM must produce, and the envelope the API returns.

Every extracted fact carries `evidence`: the exact words from the note it came from.
That lets the validator reject anything the model invented (see validate.py).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VitalType(StrEnum):
    blood_pressure = "blood_pressure"
    heart_rate = "heart_rate"
    temperature = "temperature"
    spo2 = "spo2"
    respiratory_rate = "respiratory_rate"
    blood_glucose = "blood_glucose"
    pain_score = "pain_score"


class MedicationStatus(StrEnum):
    given = "given"
    refused = "refused"
    held = "held"
    due = "due"


class ObservationCategory(StrEnum):
    mobility = "mobility"
    nutrition = "nutrition"
    skin = "skin"
    mental_state = "mental_state"
    elimination = "elimination"
    sleep = "sleep"
    pain = "pain"
    other = "other"


class Priority(StrEnum):
    routine = "routine"
    soon = "soon"
    urgent = "urgent"


class RiskType(StrEnum):
    fall = "fall"
    pressure_injury = "pressure_injury"
    deterioration = "deterioration"
    infection = "infection"
    allergy = "allergy"
    other = "other"


EVIDENCE = Field(description="Exact words copied from the note that support this item. Never paraphrase.")
TIME = Field(default=None, description="24-hour time 'HH:MM' if the note states one, else null.")


class Patient(Strict):
    reference: str | None = Field(
        default=None, description="How the note identifies the patient, e.g. 'room 12 bed B'. Null if absent."
    )
    evidence: str | None = Field(default=None, description="Exact words naming the patient, or null.")


class Vital(Strict):
    type: VitalType
    value: float = Field(description="Main number. For blood pressure, the systolic value.")
    value2: float | None = Field(default=None, description="Diastolic value for blood pressure, else null.")
    unit: str = Field(description="Unit as normally written, e.g. 'mmHg', 'bpm', '°C', '%', '/min', 'mmol/L'.")
    time: str | None = TIME
    evidence: str = EVIDENCE


class Medication(Strict):
    name: str
    dose: str | None = Field(default=None, description="Dose with unit, e.g. '500 mg', or null.")
    route: str | None = Field(default=None, description="e.g. 'oral', 'IV', 'subcutaneous', or null.")
    status: MedicationStatus
    time: str | None = TIME
    evidence: str = EVIDENCE


class Observation(Strict):
    category: ObservationCategory
    summary: str = Field(description="One short English sentence. Translate if the note is in another language.")
    evidence: str = EVIDENCE


class Task(Strict):
    description: str = Field(description="What the next shift must do, in short English.")
    due: str | None = TIME
    priority: Priority
    evidence: str = EVIDENCE


class RiskFlag(Strict):
    type: RiskType
    detail: str = Field(description="Short English explanation.")
    evidence: str = EVIDENCE


class CareNote(Strict):
    """Structured handover note."""

    patient: Patient
    vitals: list[Vital] = Field(default_factory=list)
    medications: list[Medication] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    uncertainties: list[str] = Field(
        default_factory=list,
        description="Anything ambiguous a nurse should double-check, in short English. Empty if none.",
    )


# ---- API envelope ----


class Severity(StrEnum):
    error = "error"  # the item is wrong or invented; triggers a repair attempt
    warning = "warning"  # plausible but a human should look


class Issue(BaseModel):
    path: str = Field(description="Where in the note, e.g. 'vitals[1]'.")
    severity: Severity
    message: str


class Status(StrEnum):
    complete = "complete"  # passed every check
    needs_review = "needs_review"  # usable, but has warnings, dropped items or uncertainties
    partial = "partial"  # the LLM was unavailable or unusable; rule-based fallback only


class StructureRequest(BaseModel):
    text: str = Field(min_length=10, max_length=8000, description="The handover note, typed or transcribed.")


class StructureResult(BaseModel):
    status: Status
    note: CareNote
    issues: list[Issue]
    source: str = Field(description="'llm' or 'fallback'")
    provider: str
    model: str
    attempts: int
    latency_ms: int
