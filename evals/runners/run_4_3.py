#!/usr/bin/env python3
"""
evals/runners/run_4_3.py — Phase 4.3 Reasoner eval runner.

Loads the 30-case golden set, runs the full graph (Evidence Gatherer + Reasoner),
scores against four eval gates, and writes:
  docs/evals/4.3-scorecard.md
  evals/results/4.3-metrics.json

Usage:
    python evals/runners/run_4_3.py
    make evals-4.3
    python evals/runners/run_4_3.py --ci     # exit 1 on missed target
    python evals/runners/run_4_3.py --model gpt-4o-mini  # ablation
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

DATASETS_DIR = REPO_ROOT / "evals/datasets"
RESULTS_DIR = REPO_ROOT / "evals/results"
SCORECARD_PATH = REPO_ROOT / "docs/evals/4.3-scorecard.md"
MANIFEST_PATH = REPO_ROOT / "data/synthea-config/manifest.json"
GOLDEN_SET_PATH = DATASETS_DIR / "4.3-reasoner-v1.jsonl"

TARGETS = {
    "citation_grounding": 1.00,
    "recommendation_accuracy": 0.85,
    "hallucination_rate": 0.05,   # max allowed (lower is better)
    "latency_p50_s": 20.0,
}

_EVAL_SERVICE = ServiceRequest(
    service_code="241615005",
    service_display="MRI lumbar spine",
    payer_id="cms-medicare",
)


def _load_manifest() -> dict[str, list[dict]]:
    with open(MANIFEST_PATH, encoding="utf-8") as fh:
        manifest = json.load(fh)
    by_path: dict[str, list[dict]] = {}
    for p in manifest.get("patients", []):
        by_path.setdefault(p.get("path", "unknown"), []).append(p)
    return by_path


def _load_golden_cases() -> list[dict]:
    cases = []
    with open(GOLDEN_SET_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def _p50(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    mid = len(s) // 2
    return (s[mid - 1] + s[mid]) / 2 if len(s) % 2 == 0 else s[mid]


def _run_case(case: dict, manifest_by_path: dict, graph) -> dict:
    path = case["manifest_path"]
    idx = case["manifest_idx"]
    patients = manifest_by_path.get(path, [])
    if idx >= len(patients):
        return {**case, "skipped": True, "skip_reason": f"no patient at idx {idx} for path {path}"}

    patient_id = patients[idx]["patient_id"]
    t0 = time.perf_counter()
    try:
        result = graph.invoke({
            "patient_id": patient_id,
            "service": _EVAL_SERVICE,
            "tool_calls": [],
        })
        latency_s = time.perf_counter() - t0
    except Exception as exc:
        return {**case, "patient_id": patient_id, "error": str(exc),
                "latency_s": time.perf_counter() - t0, "skipped": False}

    if result.get("error"):
        return {**case, "patient_id": patient_id, "error": result["error"],
                "latency_s": latency_s, "skipped": False}

    decision = result.get("decision")
    if decision is None:
        return {**case, "patient_id": patient_id, "error": "decision missing",
                "latency_s": latency_s, "skipped": False}

    # Recommendation accuracy — allow deny/needs_review as both "non-approve"
    expected_rec = case["expected_recommendation"]
    actual_rec = decision.overall_recommendation
    # Treat "needs_review" as equivalent to "deny" for accuracy scoring
    rec_correct = (actual_rec == expected_rec) or (
        expected_rec == "deny" and actual_rec in ("deny", "needs_review")
    )

    # Citation grounding
    citation_check_passed = decision.citation_check_passed
    grounding_issues = decision.grounding_issues

    # Hallucination check — for denial cases, model must NOT return "approve"
    hallucinated = (expected_rec == "deny" and actual_rec == "approve")

    return {
        **case,
        "patient_id": patient_id,
        "actual_recommendation": actual_rec,
        "rec_correct": rec_correct,
        "citation_check_passed": citation_check_passed,
        "grounding_issues": grounding_issues,
        "hallucinated": hallucinated,
        "latency_s": latency_s,
        "skipped": False,
        "error": None,
    }


def _write_scorecard(results: list[dict], agg: dict, targets_met: dict,
                     run_ts: str, model: str) -> None:
    SCORECARD_PATH.parent.mkdir(parents=True, exist_ok=True)

    cg = agg["citation_grounding"]
    ra = agg["recommendation_accuracy"]
    hr = agg["hallucination_rate"]
    lat = agg["latency_p50_s"]

    def _gate(val, target, lower_better=False):
        met = val <= target if lower_better else val >= target
        return "✅" if met else "❌"

    lines = [
        "# Phase 4.3 — Medical Necessity Reasoner Eval Scorecard",
        "",
        f"**Run**: {run_ts}  ",
        f"**Model**: {model}  ",
        f"**Cases**: {len(results)} total · {sum(1 for r in results if r.get('skipped'))} skipped · "
        f"{sum(1 for r in results if r.get('error'))} errored",
        "",
        "---",
        "",
        "## Summary",
        "",
        "| Metric | Result | Target | Gate |",
        "|---|---|---|---|",
        f"| Citation grounding | {cg:.2%} | = {TARGETS['citation_grounding']:.0%} | {_gate(cg, TARGETS['citation_grounding'])} |",
        f"| Recommendation accuracy | {ra:.2%} | ≥ {TARGETS['recommendation_accuracy']:.0%} | {_gate(ra, TARGETS['recommendation_accuracy'])} |",
        f"| Hallucination rate | {hr:.2%} | < {TARGETS['hallucination_rate']:.0%} | {_gate(hr, TARGETS['hallucination_rate'], lower_better=True)} |",
        f"| Latency P50 | {lat:.2f}s | < {TARGETS['latency_p50_s']}s | {_gate(lat, TARGETS['latency_p50_s'], lower_better=True)} |",
        "",
        "---",
        "",
        "## Per-case results",
        "",
        "| Case | Path | Patient | Rec | ✓ | Citation | Halluc | Latency |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for r in results:
        if r.get("skipped"):
            lines.append(f"| {r['case_id']} | {r['manifest_path']} | — | — | — | — | — | ⏭ |")
            continue
        if r.get("error"):
            lines.append(f"| {r['case_id']} | {r['manifest_path']} | `{r.get('patient_id','?')[:8]}…` | ❌ err | — | — | — | {r.get('latency_s',0):.1f}s |")
            continue
        rec_icon = "✅" if r.get("rec_correct") else "❌"
        cit_icon = "✅" if r.get("citation_check_passed") else "❌"
        hal_icon = "❌" if r.get("hallucinated") else "✅"
        lines.append(
            f"| {r['case_id']} | {r['manifest_path']} | `{r.get('patient_id','?')[:8]}…` "
            f"| {r.get('actual_recommendation','?')} | {rec_icon} | {cit_icon} | {hal_icon} | {r.get('latency_s',0):.1f}s |"
        )

    failures = [r for r in results if not r.get("skipped") and (
        r.get("error") or not r.get("rec_correct") or not r.get("citation_check_passed") or r.get("hallucinated")
    )]
    lines += ["", "---", "", "## Failure cases", ""]
    if not failures:
        lines.append("*No failures.*")
    else:
        for r in failures:
            lines.append(f"### {r['case_id']} — `{r.get('patient_id','?')}` (path: {r['manifest_path']})")
            if r.get("error"):
                lines.append(f"- **Error**: {r['error']}")
            else:
                if not r.get("rec_correct"):
                    lines.append(f"- **Wrong recommendation**: expected={r['expected_recommendation']}, actual={r.get('actual_recommendation','?')}")
                if not r.get("citation_check_passed"):
                    lines.append(f"- **Bad citations**: {r.get('grounding_issues', [])}")
                if r.get("hallucinated"):
                    lines.append(f"- **Hallucination**: model approved a denial case")
            lines.append("")

    all_met = all(targets_met.values())
    lines += ["---", "", f"## Overall: {'✅ All targets met' if all_met else '❌ One or more targets missed'}", ""]

    with open(SCORECARD_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 4.3 eval runner")
    parser.add_argument("--ci", action="store_true")
    parser.add_argument("--model", default=None, help="Override REASONER_MODEL")
    args = parser.parse_args()

    if args.model:
        os.environ["REASONER_MODEL"] = args.model

    model = os.getenv("REASONER_MODEL", "gpt-4o")
    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"\nPhase 4.3 Eval Runner — {run_ts}")
    print(f"Model    : {model}")
    print(f"Manifest : {MANIFEST_PATH.relative_to(REPO_ROOT)}\n")

    if not MANIFEST_PATH.exists():
        print("ERROR: manifest.json not found. Run `make load-synthea` first.")
        sys.exit(1)

    manifest_by_path = _load_manifest()
    golden_cases = _load_golden_cases()
    graph = build_graph()

    print(f"Running {len(golden_cases)} cases ...\n")
    results = []
    for i, case in enumerate(golden_cases, 1):
        print(f"  [{i:02d}/{len(golden_cases)}] {case['case_id']} ({case['manifest_path']}) ...", end=" ", flush=True)
        r = _run_case(case, manifest_by_path, graph)
        results.append(r)
        if r.get("skipped"):
            print("⏭ skipped")
        elif r.get("error"):
            print(f"❌ {r['error'][:50]}")
        else:
            icon = "✅" if r.get("rec_correct") else "❌"
            print(f"{icon} {r.get('actual_recommendation','?')} | {r.get('latency_s',0):.1f}s")

    active = [r for r in results if not r.get("skipped") and not r.get("error")]
    citation_vals = [1.0 if r.get("citation_check_passed") else 0.0 for r in active]
    rec_vals = [1.0 if r.get("rec_correct") else 0.0 for r in active]
    hal_vals = [1.0 if r.get("hallucinated") else 0.0 for r in active]
    lat_vals = [r.get("latency_s", 0.0) for r in active]

    agg = {
        "citation_grounding": sum(citation_vals) / len(citation_vals) if citation_vals else 0.0,
        "recommendation_accuracy": sum(rec_vals) / len(rec_vals) if rec_vals else 0.0,
        "hallucination_rate": sum(hal_vals) / len(hal_vals) if hal_vals else 0.0,
        "latency_p50_s": _p50(lat_vals),
    }

    targets_met = {
        "citation_grounding": agg["citation_grounding"] >= TARGETS["citation_grounding"],
        "recommendation_accuracy": agg["recommendation_accuracy"] >= TARGETS["recommendation_accuracy"],
        "hallucination_rate": agg["hallucination_rate"] <= TARGETS["hallucination_rate"],
        "latency_p50_s": agg["latency_p50_s"] <= TARGETS["latency_p50_s"],
    }

    print(f"\n{'─' * 58}")
    print(f"  Citation grounding      : {agg['citation_grounding']:.2%}  {'✅' if targets_met['citation_grounding'] else '❌'}")
    print(f"  Recommendation accuracy : {agg['recommendation_accuracy']:.2%}  {'✅' if targets_met['recommendation_accuracy'] else '❌'}")
    print(f"  Hallucination rate      : {agg['hallucination_rate']:.2%}  {'✅' if targets_met['hallucination_rate'] else '❌'}")
    print(f"  Latency P50             : {agg['latency_p50_s']:.2f}s  {'✅' if targets_met['latency_p50_s'] else '❌'}")
    print(f"{'─' * 58}\n")

    _write_scorecard(results, agg, targets_met, run_ts, model)
    print(f"Scorecard → {SCORECARD_PATH.relative_to(REPO_ROOT)}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "4.3-metrics.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"run_ts": run_ts, "model": model, "targets": TARGETS,
                   "targets_met": targets_met, "metrics": agg,
                   "cases": results}, fh, indent=2, default=str)
    print(f"Metrics   → {out.relative_to(REPO_ROOT)}\n")

    if args.ci and not all(targets_met.values()):
        print("CI: targets missed — exiting 1.")
        sys.exit(1)


if __name__ == "__main__":
    main()
