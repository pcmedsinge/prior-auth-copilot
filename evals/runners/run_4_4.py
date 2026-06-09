#!/usr/bin/env python3
"""
evals/runners/run_4_4.py — Phase 4.4 Bundle Builder eval runner.

Runs the pipeline up to (but not including) the Reviewer interrupt for each
golden case, then checks:
  - Bundle structural validity (Claim + Provenance present)
  - $validate pass rate against payer HAPI (if running)
  - Reviewer round-trip latency < 5s (machine-side only)
  - Audit trail: every Bundle has a Provenance resource

Usage:
    python evals/runners/run_4_4.py
    make evals-4.4
"""

from __future__ import annotations

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
SCORECARD_PATH = REPO_ROOT / "docs/evals/4.4-scorecard.md"
MANIFEST_PATH = REPO_ROOT / "data/synthea-config/manifest.json"
GOLDEN_SET_PATH = DATASETS_DIR / "4.4-bundle-v1.jsonl"

TARGETS = {
    "validation_pass_rate": 1.00,
    "has_claim_rate": 1.00,
    "has_provenance_rate": 1.00,
    "latency_p50_s": 5.0,
}

_EVAL_SERVICE = ServiceRequest(
    service_code="241615005",
    service_display="MRI lumbar spine",
    payer_id="cms-medicare",
)


def _load_manifest():
    with open(MANIFEST_PATH) as fh:
        m = json.load(fh)
    by_path = {}
    for p in m.get("patients", []):
        by_path.setdefault(p["path"], []).append(p)
    return by_path


def _p50(vals):
    if not vals:
        return 0.0
    s = sorted(vals)
    mid = len(s) // 2
    return (s[mid - 1] + s[mid]) / 2 if len(s) % 2 == 0 else s[mid]


def _run_case(case, manifest_by_path, graph):
    path, idx = case["manifest_path"], case["manifest_idx"]
    patients = manifest_by_path.get(path, [])
    if idx >= len(patients):
        return {**case, "skipped": True, "skip_reason": f"no patient idx {idx} for path {path}"}

    patient_id = patients[idx]["patient_id"]
    t0 = time.perf_counter()
    try:
        # Run without checkpointer (no HITL interrupt in evals)
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

    env = result.get("bundle_envelope")
    if env is None:
        return {**case, "patient_id": patient_id, "error": "bundle_envelope missing",
                "latency_s": latency_s, "skipped": False}

    entries = env.bundle.get("entry", [])
    resource_types = [e.get("resource", {}).get("resourceType") for e in entries]
    has_claim = "Claim" in resource_types
    has_provenance = "Provenance" in resource_types

    return {
        **case,
        "patient_id": patient_id,
        "validation_passed": env.validation_passed,
        "has_claim": has_claim,
        "has_provenance": has_provenance,
        "entry_count": len(entries),
        "latency_s": latency_s,
        "skipped": False,
        "error": None,
    }


def _write_scorecard(results, agg, targets_met, run_ts):
    SCORECARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    vr = agg["validation_pass_rate"]
    cr = agg["has_claim_rate"]
    pr = agg["has_provenance_rate"]
    lat = agg["latency_p50_s"]

    def _g(val, target, low=False):
        return "✅" if (val <= target if low else val >= target) else "❌"

    lines = [
        "# Phase 4.4 — PAS Bundle Builder Eval Scorecard",
        "",
        f"**Run**: {run_ts}",
        f"**Cases**: {len(results)}",
        "",
        "---",
        "",
        "## Summary",
        "",
        "| Metric | Result | Target | Gate |",
        "|---|---|---|---|",
        f"| $validate pass rate | {vr:.2%} | = {TARGETS['validation_pass_rate']:.0%} | {_g(vr, TARGETS['validation_pass_rate'])} |",
        f"| Has Claim resource | {cr:.2%} | = {TARGETS['has_claim_rate']:.0%} | {_g(cr, TARGETS['has_claim_rate'])} |",
        f"| Has Provenance resource | {pr:.2%} | = {TARGETS['has_provenance_rate']:.0%} | {_g(pr, TARGETS['has_provenance_rate'])} |",
        f"| Reviewer round-trip P50 | {lat:.2f}s | < {TARGETS['latency_p50_s']}s | {_g(lat, TARGETS['latency_p50_s'], low=True)} |",
        "",
        "---",
        "",
        "## Per-case results",
        "",
        "| Case | Path | Patient | Valid | Claim | Prov | Latency | Status |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for r in results:
        if r.get("skipped"):
            lines.append(f"| {r['case_id']} | {r['manifest_path']} | — | — | — | — | — | ⏭ |")
            continue
        if r.get("error"):
            lines.append(f"| {r['case_id']} | {r['manifest_path']} | `{r.get('patient_id','?')[:8]}…` | ❌ | ❌ | ❌ | {r.get('latency_s',0):.1f}s | ❌ err |")
            continue
        ok = r.get("validation_passed") and r.get("has_claim") and r.get("has_provenance")
        lines.append(
            f"| {r['case_id']} | {r['manifest_path']} | `{r.get('patient_id','?')[:8]}…` "
            f"| {'✅' if r.get('validation_passed') else '⚠️'} "
            f"| {'✅' if r.get('has_claim') else '❌'} "
            f"| {'✅' if r.get('has_provenance') else '❌'} "
            f"| {r.get('latency_s',0):.1f}s | {'✅' if ok else '❌'} |"
        )

    all_met = all(targets_met.values())
    lines += ["", "---", "", f"## Overall: {'✅ All targets met' if all_met else '❌ Targets missed'}", ""]
    with open(SCORECARD_PATH, "w") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    print(f"\nPhase 4.4 Eval Runner — {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n")

    if not MANIFEST_PATH.exists():
        print("ERROR: run `make load-synthea` first.")
        sys.exit(1)

    manifest = _load_manifest()
    cases = [json.loads(l) for l in open(GOLDEN_SET_PATH) if l.strip()]
    # No checkpointer in evals — graph runs Intake→Evidence→Reason→Bundle→Validate then END
    graph = build_graph()

    print(f"Running {len(cases)} cases ...\n")
    results = []
    for i, case in enumerate(cases, 1):
        print(f"  [{i:02d}/{len(cases)}] {case['case_id']} ...", end=" ", flush=True)
        r = _run_case(case, manifest, graph)
        results.append(r)
        if r.get("skipped"):
            print("⏭")
        elif r.get("error"):
            print(f"❌ {r['error'][:50]}")
        else:
            print(f"valid={'✅' if r.get('validation_passed') else '⚠️'} claim={'✅' if r.get('has_claim') else '❌'} prov={'✅' if r.get('has_provenance') else '❌'} {r.get('latency_s',0):.1f}s")

    active = [r for r in results if not r.get("skipped") and not r.get("error")]
    agg = {
        "validation_pass_rate": sum(1.0 if r.get("validation_passed") else 0.0 for r in active) / len(active) if active else 0.0,
        "has_claim_rate": sum(1.0 if r.get("has_claim") else 0.0 for r in active) / len(active) if active else 0.0,
        "has_provenance_rate": sum(1.0 if r.get("has_provenance") else 0.0 for r in active) / len(active) if active else 0.0,
        "latency_p50_s": _p50([r.get("latency_s", 0) for r in active]),
    }
    targets_met = {
        "validation_pass_rate": agg["validation_pass_rate"] >= TARGETS["validation_pass_rate"],
        "has_claim_rate": agg["has_claim_rate"] >= TARGETS["has_claim_rate"],
        "has_provenance_rate": agg["has_provenance_rate"] >= TARGETS["has_provenance_rate"],
        "latency_p50_s": agg["latency_p50_s"] <= TARGETS["latency_p50_s"],
    }

    print(f"\n{'─'*55}")
    for k, v in agg.items():
        icon = "✅" if targets_met[k] else "❌"
        print(f"  {k:<30} : {v:.2f}  {icon}")
    print(f"{'─'*55}\n")

    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_scorecard(results, agg, targets_met, run_ts)
    print(f"Scorecard → {SCORECARD_PATH.relative_to(REPO_ROOT)}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "4.4-metrics.json"
    with open(out, "w") as fh:
        json.dump({"run_ts": run_ts, "targets": TARGETS, "targets_met": targets_met, "metrics": agg, "cases": results}, fh, indent=2, default=str)
    print(f"Metrics   → {out.relative_to(REPO_ROOT)}\n")


if __name__ == "__main__":
    main()
