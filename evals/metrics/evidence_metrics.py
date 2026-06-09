"""
evals/metrics/evidence_metrics.py

Four metric functions for the Phase 4.2 evidence-retrieval eval harness.

All functions take a CaseResult (produced by the runner) and return a float 0–1
(or a float in seconds for latency).  Aggregation is handled by the runner.

Metrics
-------
1. tool_call_accuracy  — were all 6 tools called without error?  (0 or 1 per case)
2. checklist_recall    — fraction of expected-true criteria correctly identified
3. citation_grounding  — fraction of resource_refs that are valid FHIR refs
4. latency_seconds     — end-to-end wall-clock seconds (raw; runner computes P50)

Targets (from docs/phases/4.2-evidence-retrieval.md)
-----------------------------------------------------
  tool_call_accuracy  >= 0.90  (mean over 20 cases)
  checklist_recall    == 1.00  (mean over 20 cases)
  citation_grounding  == 1.00  (mean over 20 cases)
  latency P50         <  8.0s
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# FHIR logical reference pattern: ResourceType/id
_FHIR_REF_RE = re.compile(r"^[A-Z][a-zA-Z]+/[a-zA-Z0-9\-\.]+$")


@dataclass
class CaseResult:
    """Result of running the graph on one golden-set case."""

    case_id: str
    manifest_path: str
    patient_id: str
    expected_criteria: dict[str, bool]
    skipped: bool = False
    skip_reason: str = ""
    error: str | None = None
    latency_s: float = 0.0

    # From EvidencePackage
    checklist_result: dict[str, bool] = field(default_factory=dict)
    resource_refs: list[str] = field(default_factory=list)
    tool_errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Metric 1 — Tool-call accuracy
# ---------------------------------------------------------------------------


def tool_call_accuracy(result: CaseResult) -> float:
    """
    1.0 if all 6 tools ran without error and no graph-level error occurred.
    0.0 otherwise.
    """
    if result.skipped or result.error:
        return 0.0
    return 0.0 if result.tool_errors else 1.0


# ---------------------------------------------------------------------------
# Metric 2 — Checklist recall (must-have resources)
# ---------------------------------------------------------------------------


def checklist_recall(result: CaseResult) -> float:
    """
    Fraction of expected-true criteria that were correctly identified as met.

    Only criteria expected to be TRUE are scored (false-expected criteria are
    not penalised for being correctly identified as unmet — that's precision,
    a separate concern).

    Returns 1.0 if no expected-true criteria exist (vacuously satisfied).
    """
    if result.skipped or result.error:
        return 0.0

    expected_true = [c for c, v in result.expected_criteria.items() if v]
    if not expected_true:
        return 1.0

    correct = sum(
        1 for c in expected_true if result.checklist_result.get(c, False)
    )
    return correct / len(expected_true)


# ---------------------------------------------------------------------------
# Metric 3 — Citation grounding
# ---------------------------------------------------------------------------


def citation_grounding(result: CaseResult) -> float:
    """
    Fraction of resource_refs that are valid FHIR logical references.

    A valid ref matches ResourceType/id (e.g. "Condition/abc-123").
    If no refs are present, returns 1.0 (nothing to fabricate).

    Note: since resource_refs are constructed directly from HAPI-returned
    resources via _fhir_ref(), fabrication is structurally prevented at the
    tool level.  This metric catches any future regression where a ref is
    assembled incorrectly (e.g. from LLM output rather than raw FHIR).
    """
    if result.skipped or result.error:
        return 0.0
    if not result.resource_refs:
        return 1.0

    valid = sum(1 for ref in result.resource_refs if _FHIR_REF_RE.match(ref))
    return valid / len(result.resource_refs)


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------


def aggregate(values: list[float]) -> dict[str, Any]:
    """Return mean, min, max for a list of metric values."""
    if not values:
        return {"mean": 0.0, "min": 0.0, "max": 0.0, "n": 0}
    return {
        "mean": sum(values) / len(values),
        "min": min(values),
        "max": max(values),
        "n": len(values),
    }


def p50(latencies: list[float]) -> float:
    """Median (P50) of a list of latency values in seconds."""
    if not latencies:
        return 0.0
    sorted_vals = sorted(latencies)
    mid = len(sorted_vals) // 2
    if len(sorted_vals) % 2 == 0:
        return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2
    return sorted_vals[mid]
