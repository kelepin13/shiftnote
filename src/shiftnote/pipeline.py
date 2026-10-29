"""Note in, validated structured note out.

LLM call (JSON schema) -> parse -> validate against the note
    -> errors? send them back and ask for a corrected answer (up to max_attempts)
    -> still errors? drop the offending items and mark the note for review
Provider down, timing out or never producing parseable output?
    -> rule-based fallback, marked `partial`. The nurse always gets something.
"""

from __future__ import annotations

import json
import logging
import time

from pydantic import ValidationError

from .fallback import extract_rule_based
from .models import CareNote, Issue, Severity, Status, StructureResult
from .prompt import SYSTEM_PROMPT, repair_prompt, user_prompt
from .providers import LLMProvider, Message, ProviderError
from .schema import care_note_schema
from .validate import error_messages, validate

log = logging.getLogger("shiftnote")

LIST_FIELDS = ("vitals", "medications", "observations", "tasks", "risk_flags")


def _schema_problems(error: ValidationError) -> list[str]:
    return [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in error.errors()[:20]]


def _drop_invalid(note: CareNote, issues: list[Issue]) -> tuple[CareNote, list[Issue]]:
    """Remove items that still have errors after all repair attempts; report each removal."""
    bad = {i.path for i in issues if i.severity is Severity.error}
    data = note.model_dump()
    for field in LIST_FIELDS:
        data[field] = [item for idx, item in enumerate(data[field]) if f"{field}[{idx}]" not in bad]
    if "patient" in bad:
        data["patient"] = {"reference": None, "evidence": None}
    cleaned = CareNote.model_validate(data)
    reported = [
        Issue(path=i.path, severity=Severity.warning, message=f"Removed: {i.message}")
        if i.severity is Severity.error
        else i
        for i in issues
    ]
    return cleaned, reported


async def structure_note(text: str, provider: LLMProvider, max_attempts: int = 2) -> StructureResult:
    started = time.perf_counter()

    def result(status: Status, note: CareNote, issues: list[Issue], source: str, attempts: int):
        return StructureResult(
            status=status,
            note=note,
            issues=issues,
            source=source,
            provider=provider.name,
            model=provider.model,
            attempts=attempts,
            latency_ms=round((time.perf_counter() - started) * 1000),
        )

    messages: list[Message] = [{"role": "user", "content": user_prompt(text)}]
    last_note: CareNote | None = None
    last_issues: list[Issue] = []
    attempt = 0

    try:
        for attempt in range(1, max_attempts + 1):
            raw = await provider.complete_json(SYSTEM_PROMPT, messages, care_note_schema())
            try:
                note = CareNote.model_validate(raw)
            except ValidationError as e:
                problems = _schema_problems(e)
            else:
                issues = validate(note, text)
                problems = error_messages(issues)
                last_note, last_issues = note, issues
                if not problems:
                    has_warnings = any(i.severity is Severity.warning for i in issues)
                    status = Status.needs_review if has_warnings or note.uncertainties else Status.complete
                    return result(status, note, issues, "llm", attempt)

            # Ask the model to fix exactly what was wrong, showing it its own previous answer.
            log.info("attempt %d had %d problem(s); asking for a repair", attempt, len(problems))
            messages += [
                {"role": "assistant", "content": json.dumps(raw)},
                {"role": "user", "content": repair_prompt(problems)},
            ]
    except ProviderError as e:
        # Never log the note itself: it is patient data.
        log.warning("provider failed (%s); using rule-based fallback", e)
        fallback = extract_rule_based(text)
        fallback, issues = _drop_invalid(fallback, validate(fallback, text))
        return result(Status.partial, fallback, issues, "fallback", attempt)

    if last_note is not None:
        cleaned, issues = _drop_invalid(last_note, last_issues)
        return result(Status.needs_review, cleaned, issues, "llm", attempt)

    log.warning("no schema-valid answer after %d attempts; using rule-based fallback", attempt)
    fallback = extract_rule_based(text)
    fallback, issues = _drop_invalid(fallback, validate(fallback, text))
    return result(Status.partial, fallback, issues, "fallback", attempt)
