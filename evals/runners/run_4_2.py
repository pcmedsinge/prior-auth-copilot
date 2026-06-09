#!/usr/bin/env python3
"""
evals/runners/run_4_2.py — Phase 4.2 evidence-retrieval eval runner.

Loads the golden set, runs the LangGraph graph on each case, scores against
the four eval-gate metrics, and writes:
  docs/evals/4.2-scorecard.md   — human-readable scorecard
  evals/results/4.2-metrics.json — machine-readable metrics

Usage:
    python evals/runners/run_4_2.py
    make evals-4.2

    # CI mode — exits 1 if any target is missed:
    python evals/runners/run_4_2.py --ci

    # Skip LLM second pass (faster, tests deterministic checklist only):
    python evals/runners/run_4_2.py --no-llm

Prerequisites:
    make fhir-up && make load-synthea
    OPENAI_API_KEY set (unless --no-llm)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(REPO_ROOT / ".env", override=False)
sys.path.insert(0, str(REPO_ROOT / "src"))

from prior_auth_copilot.graph import build_graph  # noqa: E402
from prior_auth_copilot.state import ServiceRequest  # noqa: E402
from evals.metrics.evidence_metrics import (  # noqa: E402
    CaseResult,
    aggregate,
    checklist_recall,
    citation_grounding,
    p50,
    tool_call_accuracy,
)

DATASETS_DIR = REPO_ROOT / "evals/datasets"
RESULTS_DIR = REPO_ROOT / "evals/results"
SCORECARD_PATH = REPO_ROOT / "docs/evals/4.2-scorecard.md"
MANIFEST_PATH = REPO_ROOT / "data/synthea-config/manifest.json"
GOLDEN_SET_PATH = DATASETS_DIR / "4.2-evidence-v1.jsonl"

# Eval gate targets
TARGETS = {
    "tool_call_accuracy": 0.90,
    "checklist_recall": 1.00,
    "citation_grounding": 1.00,
    "latency_p50_s": 8.0,
}

# Fixed service for all eval cases
_EVAL_SERVICE = ServiceRequest(
    service_code="241615005",
    service_display="MRI lumbar spine",
    payer_id="eval-payer",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_manifest() -> dict[str, list[dict]]:
    """Load manifest and group patients by path."""
    with open(MANIFEST_PATH, encoding="utf-8") as fh:
        manifest = json.load(fh)
    by_path: dict[str, list[dict]] = {}
    for p in manifest.get("patients", []):
        path = p.get("path", "unknown")
        by_path.setdefault(path, []).append(p)
    return by_path


def _load_golden_cases() -> list[dict]:
    cases = []
    with open(GOLDEN_SET_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def _run_case(
    case: dict,
    manifest_by_path: dict[str, list[dict]],
    graph,
    no_llm: bool,
) -> CaseResult:
    """Run one golden case and return a scored CaseResult."""
    case_id = case["case_id"]
    path = case["manifest_path"]
    idx = case["manifest_idx"]
    expected = case["expected_criteria"]

    # Find patient
    patients_for_path = manifest_by_path.get(path, [])
    if idx >= len(patients_for_path):
        return CaseResult(
            case_id=case_id,
            manifest_path=path,
            patient_id="",
            expected_criteria=expected,
            skipped=True,
            skip_reason=f"manifest has only {len(patients_for_path)} patient(s) for path '{path}'; idx {idx} not available",
        )

    patient_id = patients_for_path[idx]["patient_id"]

    # Optionally patch env to disable LLM
    if no_llm:
        os.environ["OPENAI_API_KEY"] = "sk-disabled-no-llm-mode"

    initial_state = {
        "patient_id": patient_id,
        "service": _EVAL_SERVICE,
        "tool_calls": [],
    }

    t0 = time.perf_counter()
    try:
        result_state = graph.invoke(initial_state)
        latency_s = time.perf_counter() - t0
    except Exception as exc:
        return CaseResult(
            case_id=case_id,
            manifest_path=path,
            patient_id=patient_id,
            expected_criteria=expected,
            error=str(exc),
            latency_s=time.perf_counter() - t0,
        )

    if result_state.get("error"):
        return CaseResult(
            case_id=case_id,
            manifest_path=path,
            patient_id=patient_id,
            expected_criteria=expected,
            error=result_state["error"],
            latency_s=latency_s,
        )

    pkg = result_state.get("evidence_package")
    if pkg is None:
        return CaseResult(
            case_id=case_id,
            manifest_path=path,
            patient_id=patient_id,
            expected_criteria=expected,
            error="evidence_package missing from result state",
            latency_s=latency_s,
        )

    # Extract checklist results
    checklist_result: dict[str, bool] = {}
    for item in pkg.checklist.items:
        # Map criterion names to short keys matching the golden set
        name = item.criterion
        if "Low back pain" in name:
            checklist_result["lbp_diagnosis"] = item.met
        elif "NSAID" in name:
            checklist_result["nsaid_prescribed"] = item.met
        elif "Physical therapy" in name:
            checklist_result["physical_therapy"] = item.met
        elif "Pain severity" in name:
            checklist_result["pain_score"] = item.met
        elif "radiculopathy" in name.lower() or "Neurological" in name:
            checklist_result["neurological_deficit"] = item.met

    resource_refs = [item.resource_ref for item in pkg.items]
    tool_errors = [
        tc.tool_name for tc in pkg.tool_calls if tc.error
    ]

    return CaseResult(
        case_id=case_id,
        manifest_path=path,
        patient_id=patient_id,
        expected_criteria=expected,
        latency_s=latency_s,
        checklist_result=checklist_result,
        resource_refs=resource_refs,
        tool_errors=tool_errors,
    )


# ---------------------------------------------------------------------------
# Scorecard writer
# ---------------------------------------------------------------------------


def _write_scorecard(
    results: list[CaseResult],
    agg_metrics: dict,
    targets_met: dict[str, bool],
    run_ts: str,
    no_llm: bool,
) -> None:
    SCORECARD_PATH.parent.mkdir(parents=True, exist_ok=True)

    tca = agg_metrics["tool_call_accuracy"]["mean"]
    cr = agg_metrics["checklist_recall"]["mean"]
    cg = agg_metrics["citation_grounding"]["mean"]
    lat = agg_metrics["latency_p50_s"]

    def _gate(val: float, target: float, higher_is_better: bool = True) -> str:
        met = val >= target if higher_is_better else val <= target
        return "✅" if met else "❌"

    lines = [
        "# Phase 4.2 — Evidence Retrieval Eval Scorecard",
        "",
        f"**Run**: {run_ts}  ",
        f"**LLM second pass**: {'disabled (--no-llm)' if no_llm else 'enabled (gpt-4o-mini)'}  ",
        f"**Cases**: {len(results)} total · {sum(1 for r in results if r.skipped)} skipped · {sum(1 for r in results if r.error)} errored",
        "",
        "---",
        "",
        "## Summary",
        "",
        "| Metric | Result | Target | Gate |",
        "|---|---|---|---|",
        f"| Tool-call accuracy | {tca:.2%} | ≥ {TARGETS['tool_call_accuracy']:.0%} | {_gate(tca, TARGETS['tool_call_accuracy'])} |",
        f"| Checklist recall | {cr:.2%} | = {TARGETS['checklist_recall']:.0%} | {_gate(cr, TARGETS['checklist_recall'])} |",
        f"| Citation grounding | {cg:.2%} | = {TARGETS['citation_grounding']:.0%} | {_gate(cg, TARGETS['citation_grounding'])} |",
        f"| End-to-end latency (P50) | {lat:.2f}s | < {TARGETS['latency_p50_s']}s | {_gate(lat, TARGETS['latency_p50_s'], higher_is_better=False)} |",
        "",
        "---",
        "",
        "## Per-case results",
        "",
        "| Case | Path | Patient | Tool ✓ | Recall | Grounding | Latency | Status |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for r in results:
        if r.skipped:
            lines.append(f"| {r.case_id} | {r.manifest_path} | — | — | — | — | — | ⏭ skipped: {r.skip_reason[:40]} |")
            continue
        if r.error:
            lines.append(f"| {r.case_id} | {r.manifest_path} | `{r.patient_id[:8]}…` | ❌ | — | — | {r.latency_s:.2f}s | ❌ error |")
            continue

        tc_score = tool_call_accuracy(r)
        rc_score = checklist_recall(r)
        cg_score = citation_grounding(r)
        overall = "✅" if (tc_score == 1.0 and rc_score == 1.0 and cg_score == 1.0) else "❌"
        lines.append(
            f"| {r.case_id} | {r.manifest_path} | `{r.patient_id[:8]}…` "
            f"| {'✅' if tc_score == 1.0 else '❌'} "
            f"| {rc_score:.0%} "
            f"| {cg_score:.0%} "
            f"| {r.latency_s:.2f}s "
            f"| {overall} |"
        )

    # Failure section
    failures = [r for r in results if not r.skipped and (r.error or checklist_recall(r) < 1.0 or citation_grounding(r) < 1.0)]
    lines += ["", "---", "", "## Failure cases", ""]
    if not failures:
        lines.append("*No failures.*")
    else:
        for r in failures:
            lines.append(f"### {r.case_id} — `{r.patient_id}` (path: {r.manifest_path})")
            if r.error:
                lines.append(f"- **Error**: {r.error}")
            else:
                missed = [c for c, v in r.expected_criteria.items() if v and not r.checklist_result.get(c, False)]
                if missed:
                    lines.append(f"- **Missing criteria**: {', '.join(missed)}")
                bad_refs = [ref for ref in r.resource_refs if not __import__('re').match(r"^[A-Z][a-zA-Z]+/[a-zA-Z0-9\-\.]+$", ref)]
                if bad_refs:
                    lines.append(f"- **Invalid refs**: {bad_refs}")
            lines.append("")

    # All-targets summary
    all_met = all(targets_met.values())
    lines += [
        "---",
        "",
        f"## Overall: {'✅ All targets met' if all_met else '❌ One or more targets missed'}",
        "",
    ]

    with open(SCORECARD_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 4.2 eval runner")
    parser.add_argument("--ci", action="store_true", help="Exit 1 if any target is missed")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM second pass (faster)")
    args = parser.parse_args()

    print(f"\nPhase 4.2 Eval Runner — {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print(f"Golden set : {GOLDEN_SET_PATH.relative_to(REPO_ROOT)}")
    print(f"Manifest   : {MANIFEST_PATH.relative_to(REPO_ROOT)}")
    print(f"LLM pass   : {'disabled' if args.no_llm else 'enabled'}\n")

    if not MANIFEST_PATH.exists():
        print("ERROR: manifest.json not found. Run `make load-synthea` first.")
        sys.exit(1)

    manifest_by_path = _load_manifest()
    golden_cases = _load_golden_cases()
    graph = build_graph()

    print(f"Running {len(golden_cases)} cases ...\n")
    results: list[CaseResult] = []
    for i, case in enumerate(golden_cases, 1):
        print(f"  [{i:02d}/{len(golden_cases)}] {case['case_id']} ({case['manifest_path']} idx={case['manifest_idx']}) ...", end=" ", flush=True)
        result = _run_case(case, manifest_by_path, graph, no_llm=args.no_llm)
        results.append(result)
        if result.skipped:
            print(f"⏭ skipped")
        elif result.error:
            print(f"❌ error: {result.error[:60]}")
        else:
            rc = checklist_recall(result)
            print(f"✓ {result.latency_s:.1f}s recall={rc:.0%}")

    # Aggregate metrics (exclude skipped)
    active = [r for r in results if not r.skipped]
    tca_vals = [tool_call_accuracy(r) for r in active]
    cr_vals = [checklist_recall(r) for r in active]
    cg_vals = [citation_grounding(r) for r in active]
    lat_vals = [r.latency_s for r in active if not r.error]

    agg = {
        "tool_call_accuracy": aggregate(tca_vals),
        "checklist_recall": aggregate(cr_vals),
        "citation_grounding": aggregate(cg_vals),
        "latency_p50_s": p50(lat_vals),
        "latency_mean_s": sum(lat_vals) / len(lat_vals) if lat_vals else 0.0,
    }

    targets_met = {
        "tool_call_accuracy": agg["tool_call_accuracy"]["mean"] >= TARGETS["tool_call_accuracy"],
        "checklist_recall": agg["checklist_recall"]["mean"] >= TARGETS["checklist_recall"],
        "citation_grounding": agg["citation_grounding"]["mean"] >= TARGETS["citation_grounding"],
        "latency_p50_s": agg["latency_p50_s"] <= TARGETS["latency_p50_s"],
    }

    # Print summary
    print(f"\n{'─' * 55}")
    print(f"  Tool-call accuracy : {agg['tool_call_accuracy']['mean']:.2%}  (target ≥ {TARGETS['tool_call_accuracy']:.0%})  {'✅' if targets_met['tool_call_accuracy'] else '❌'}")
    print(f"  Checklist recall   : {agg['checklist_recall']['mean']:.2%}  (target = {TARGETS['checklist_recall']:.0%})  {'✅' if targets_met['checklist_recall'] else '❌'}")
    print(f"  Citation grounding : {agg['citation_grounding']['mean']:.2%}  (target = {TARGETS['citation_grounding']:.0%})  {'✅' if targets_met['citation_grounding'] else '❌'}")
    print(f"  Latency P50        : {agg['latency_p50_s']:.2f}s  (target < {TARGETS['latency_p50_s']}s)  {'✅' if targets_met['latency_p50_s'] else '❌'}")
    print(f"{'─' * 55}\n")

    # Write outputs
    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_scorecard(results, agg, targets_met, run_ts, no_llm=args.no_llm)
    print(f"Scorecard  → {SCORECARD_PATH.relative_to(REPO_ROOT)}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    metrics_out = RESULTS_DIR / "4.2-metrics.json"
    with open(metrics_out, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "run_ts": run_ts,
                "targets": TARGETS,
                "targets_met": targets_met,
                "metrics": {k: v for k, v in agg.items()},
                "cases": [
                    {
                        "case_id": r.case_id,
                        "manifest_path": r.manifest_path,
                        "patient_id": r.patient_id,
                        "skipped": r.skipped,
                        "error": r.error,
                        "latency_s": r.latency_s,
                        "tool_call_accuracy": tool_call_accuracy(r),
                        "checklist_recall": checklist_recall(r),
                        "citation_grounding": citation_grounding(r),
                    }
                    for r in results
                ],
            },
            fh,
            indent=2,
        )
    print(f"Metrics    → {metrics_out.relative_to(REPO_ROOT)}\n")

    all_met = all(targets_met.values())
    if args.ci and not all_met:
        print("CI mode: one or more eval targets missed — exiting 1.")
        sys.exit(1)

    if all_met:
        print("All eval targets met. ✅\n")
    else:
        missed = [k for k, v in targets_met.items() if not v]
        print(f"Targets missed: {missed}\n")


if __name__ == "__main__":
    main()
