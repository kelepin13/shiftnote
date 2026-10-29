"""Evaluation suite: run every annotated case through the real pipeline and score it.

    python -m shiftnote.evals                      # uses SHIFTNOTE_PROVIDER (mock by default)
    SHIFTNOTE_PROVIDER=openai SHIFTNOTE_API_KEY=... python -m shiftnote.evals --out evals/report-openai.md

Each case in evals/cases/*.json is a synthetic handover note with the facts a nurse would expect
to see extracted. The report shows, per case and overall:
- vitals precision / recall (type and value must match)
- medications recall, and whether the status (given / refused / held) was right
- tasks recall (did the next shift's to-dos survive?)
- risk-flag precision / recall
- whether ambiguous notes were flagged instead of guessed
- how many invented or invalid items the validator caught and removed
- status mix, attempts and latency
Use it to compare prompts, models and providers with numbers instead of impressions.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Settings
from .models import StructureResult
from .pipeline import structure_note
from .providers import LLMProvider, build_provider

# Works from a source checkout (repo root) and from the Docker image (/app).
DEFAULT_CASES = next(
    (
        p
        for p in (Path.cwd() / "evals" / "cases", Path(__file__).resolve().parents[2] / "evals" / "cases")
        if p.is_dir()
    ),
    Path("evals/cases"),
)


@dataclass
class Counts:
    hit: int = 0
    predicted: int = 0
    expected: int = 0

    def add(self, other: Counts) -> None:
        self.hit += other.hit
        self.predicted += other.predicted
        self.expected += other.expected

    @property
    def precision(self) -> float | None:
        return self.hit / self.predicted if self.predicted else None

    @property
    def recall(self) -> float | None:
        return self.hit / self.expected if self.expected else None


@dataclass
class CaseScore:
    id: str
    status: str
    source: str
    attempts: int
    latency_ms: int
    vitals: Counts
    meds: Counts
    med_status_right: int
    tasks: Counts
    risks: Counts
    removed: int
    uncertainty_ok: bool | None
    notes: list[str] = field(default_factory=list)


def _close(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) < 0.051


def score_case(case: dict[str, Any], result: StructureResult) -> CaseScore:
    exp = case["expected"]
    note = result.note
    notes: list[str] = []

    # Vitals: one-to-one match on type + value(s).
    remaining = list(note.vitals)
    v_hit = 0
    for e in exp["vitals"]:
        match = next(
            (
                v
                for v in remaining
                if v.type == e["type"]
                and _close(v.value, e["value"])
                and (e.get("value2") is None or _close(v.value2, e["value2"]))
            ),
            None,
        )
        if match:
            v_hit += 1
            remaining.remove(match)
        else:
            notes.append(f"missed vital {e['type']} {e['value']}")
    for extra in remaining:
        notes.append(f"unexpected vital {extra.type} {extra.value:g}")

    # Medications: name match either way round; status scored on matched ones.
    m_hit = status_right = 0
    for e in exp["medications"]:
        match = next((m for m in note.medications if e["name"] in m.name.lower() or m.name.lower() in e["name"]), None)
        if match:
            m_hit += 1
            if match.status == e["status"]:
                status_right += 1
            else:
                notes.append(f"{e['name']}: status {match.status}, expected {e['status']}")
        else:
            notes.append(f"missed medication {e['name']}")

    # Tasks: an expected keyword must appear in some task, and the due time must match if annotated.
    t_hit = 0
    for e in exp["tasks"]:
        ok = any(
            e["keyword"] in t.description.lower() and (e.get("due") is None or t.due == e["due"]) for t in note.tasks
        )
        t_hit += ok
        if not ok:
            notes.append(f"missed task '{e['keyword']}'" + (f" by {e['due']}" if e.get("due") else ""))

    # Risk flags: set comparison.
    got = {f.type.value for f in note.risk_flags}
    want = set(exp["risk_flags"])
    for missing in want - got:
        notes.append(f"missed risk {missing}")
    for extra in got - want:
        notes.append(f"extra risk {extra}")

    uncertainty_ok = None
    if exp.get("must_flag_uncertain"):
        guessed = any(m.dose for m in note.medications if "morphine" in m.name.lower())
        uncertainty_ok = bool(note.uncertainties) and not guessed
        if not uncertainty_ok:
            notes.append("ambiguous dose was guessed or not flagged")

    return CaseScore(
        id=case["id"],
        status=result.status.value,
        source=result.source,
        attempts=result.attempts,
        latency_ms=result.latency_ms,
        vitals=Counts(v_hit, len(note.vitals), len(exp["vitals"])),
        meds=Counts(m_hit, len(note.medications), len(exp["medications"])),
        med_status_right=status_right,
        tasks=Counts(t_hit, len(note.tasks), len(exp["tasks"])),
        risks=Counts(len(got & want), len(got), len(want)),
        removed=sum(1 for i in result.issues if i.message.startswith("Removed:")),
        uncertainty_ok=uncertainty_ok,
        notes=notes,
    )


def load_cases(directory: Path) -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.json"))]


async def run_evals(provider: LLMProvider, cases: list[dict[str, Any]], max_attempts: int = 2) -> list[CaseScore]:
    scores = []
    for case in cases:
        result = await structure_note(case["text"], provider, max_attempts=max_attempts)
        scores.append(score_case(case, result))
    return scores


def _pct(value: float | None) -> str:
    return "–" if value is None else f"{value:.0%}"


def summarize(scores: list[CaseScore]) -> dict[str, Any]:
    vitals, meds, tasks, risks = Counts(), Counts(), Counts(), Counts()
    for s in scores:
        vitals.add(s.vitals)
        meds.add(s.meds)
        tasks.add(s.tasks)
        risks.add(s.risks)
    latencies = sorted(s.latency_ms for s in scores)
    checked = [s.uncertainty_ok for s in scores if s.uncertainty_ok is not None]
    return {
        "cases": len(scores),
        "vitals_precision": vitals.precision,
        "vitals_recall": vitals.recall,
        "meds_recall": meds.recall,
        "med_status_accuracy": (sum(s.med_status_right for s in scores) / meds.hit) if meds.hit else None,
        "tasks_recall": tasks.recall,
        "risk_precision": risks.precision,
        "risk_recall": risks.recall,
        "ambiguity_flagged": (sum(checked) / len(checked)) if checked else None,
        "items_removed_by_checks": sum(s.removed for s in scores),
        "fallback_rate": sum(s.source == "fallback" for s in scores) / len(scores),
        "complete_rate": sum(s.status == "complete" for s in scores) / len(scores),
        "mean_attempts": statistics.mean(s.attempts for s in scores),
        "latency_p50_ms": latencies[len(latencies) // 2],
        "latency_p95_ms": latencies[min(len(latencies) - 1, round(0.95 * (len(latencies) - 1)))],
    }


def render_report(provider: LLMProvider, scores: list[CaseScore], summary: dict[str, Any]) -> str:
    lines = [
        f"# Shiftnote evaluation: {provider.name} ({provider.model})",
        "",
        f"{summary['cases']} synthetic handover notes in English, German and Indonesian.",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Vitals precision / recall | {_pct(summary['vitals_precision'])} / {_pct(summary['vitals_recall'])} |",
        f"| Medications found | {_pct(summary['meds_recall'])} |",
        f"| Medication status correct (given / refused / held) | {_pct(summary['med_status_accuracy'])} |",
        f"| Next-shift tasks found | {_pct(summary['tasks_recall'])} |",
        f"| Risk flags precision / recall | {_pct(summary['risk_precision'])} / {_pct(summary['risk_recall'])} |",
        f"| Ambiguous dose flagged, not guessed | {_pct(summary['ambiguity_flagged'])} |",
        f"| Invented or invalid items caught by checks | {summary['items_removed_by_checks']} |",
        f"| Fell back to rules | {_pct(summary['fallback_rate'])} |",
        f"| Passed every check first time or after repair | {_pct(summary['complete_rate'])} |",
        f"| Mean attempts per note | {summary['mean_attempts']:.2f} |",
        f"| Latency p50 / p95 | {summary['latency_p50_ms']} ms / {summary['latency_p95_ms']} ms |",
        "",
        "## Per case",
        "",
        "| Case | Status | Vitals | Meds | Tasks | Risks | Notes |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in scores:
        lines.append(
            f"| {s.id} | {s.status} | {s.vitals.hit}/{s.vitals.expected} | {s.meds.hit}/{s.meds.expected} "
            f"| {s.tasks.hit}/{s.tasks.expected} | {s.risks.hit}/{s.risks.expected} | {'; '.join(s.notes) or 'all found'} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--out", type=Path, help="write the markdown report here")
    parser.add_argument("--min-vitals-recall", type=float, default=0.0, help="exit 1 below this (for CI)")
    args = parser.parse_args(argv)

    settings = Settings()
    provider = build_provider(settings)
    scores = asyncio.run(run_evals(provider, load_cases(args.cases), settings.max_attempts))
    summary = summarize(scores)
    report = render_report(provider, scores, summary)
    print(report)
    if args.out:
        args.out.write_text(report, encoding="utf-8")
    recall = summary["vitals_recall"] or 0.0
    if recall < args.min_vitals_recall:
        print(f"vitals recall {recall:.0%} is below the minimum {args.min_vitals_recall:.0%}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
