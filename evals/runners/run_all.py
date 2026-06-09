#!/usr/bin/env python3
"""
evals/runners/run_all.py — Combined eval runner for all phases.

Chains:
  Phase 4.2 — Evidence retrieval (20 cases)
  Phase 4.3 — Medical necessity reasoner (30 cases)
  Phase 4.4 — PAS Bundle validation (10 cases)

Writes:
  docs/evals/v1.0-scorecard.md    — combined headline scorecard
  evals/results/v1.0-metrics.json — machine-readable metrics for all phases

Usage:
    python evals/runners/run_all.py
    make evals

    # Faster — skip LLM second pass for evidence gathering:
    python evals/runners/run_all.py --no-llm

    # CI mode — exits 1 if any target missed:
    python evals/runners/run_all.py --ci
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RESULTS_DIR = REPO_ROOT / "evals/results"
SCORECARD_PATH = REPO_ROOT / "docs/evals/v1.0-scorecard.md"


def _run_phase(phase: str, extra_args: list[str], label: str) -> dict | None:
    """Run a phase eval runner as a subprocess and return its metrics JSON."""
    runner = REPO_ROOT / f"evals/runners/run_{phase}.py"
    cmd = [sys.executable, str(runner)] + extra_args
    print(f"\n{'═' * 60}")
    print(f"  {label}")
    print(f"{'═' * 60}")
    result = subprocess.run(cmd, cwd=str(REPO_ROOT))
    if result.returncode not in (0, 1):  # 1 = targets missed but ran
        print(f"  [ERROR] {label} runner exited with code {result.returncode}")
        return None

    metrics_file = RESULTS_DIR / f"{phase.replace('_', '.')}-metrics.json"
    if metrics_file.exists():
        with open(metrics_file) as fh:
            return json.load(fh)
    return None


def _write_combined_scorecard(metrics: dict, run_ts: str) -> None:
    SCORECARD_PATH.parent.mkdir(parents=True, exist_ok=True)

    def _row(name, val, target, lower_better=False, pct=True):
        if val is None:
            return f"| {name} | — | {target} | — |"
        met = val <= target if lower_better else val >= target
        gate = "✅" if met else "❌"
        fmt = f"{val:.2%}" if pct else f"{val:.2f}s"
        return f"| {name} | {fmt} | {target} | {gate} |"

    m42 = metrics.get("4_2", {}).get("metrics", {})
    m43 = metrics.get("4_3", {}).get("metrics", {})
    m44 = metrics.get("4_4", {}).get("metrics", {})

    all_targets_met = all([
        m42.get("tool_call_accuracy", 0) >= 0.90,
        m42.get("checklist_recall", 0) >= 1.00,
        m42.get("citation_grounding", 0) >= 1.00,
        m43.get("citation_grounding", 0) >= 1.00,
        m43.get("recommendation_accuracy", 0) >= 0.85,
        m43.get("hallucination_rate", 1) <= 0.05,
        m44.get("validation_pass_rate", 0) >= 1.00,
        m44.get("has_provenance_rate", 0) >= 1.00,
    ])

    lines = [
        "# Prior-Auth Co-pilot — v1.0 Eval Scorecard",
        "",
        f"**Run**: {run_ts}  ",
        f"**Reasoner model**: {os.getenv('REASONER_MODEL', 'gpt-4o')}  ",
        f"**Overall**: {'✅ All gates passed' if all_targets_met else '❌ One or more gates failed'}",
        "",
        "---",
        "",
        "## Phase 4.2 — Evidence Retrieval",
        "",
        "| Metric | Result | Target | Gate |",
        "|---|---|---|---|",
        _row("Tool-call accuracy", m42.get("tool_call_accuracy"), "≥ 90%"),
        _row("Checklist recall (must-have resources)", m42.get("checklist_recall"), "= 100%"),
        _row("Citation grounding (no fabricated refs)", m42.get("citation_grounding"), "= 100%"),
        _row("End-to-end latency P50", m42.get("latency_p50_s"), "< 8s", lower_better=True, pct=False),
        "",
        "## Phase 4.3 — Medical Necessity Reasoner",
        "",
        "| Metric | Result | Target | Gate |",
        "|---|---|---|---|",
        _row("Citation grounding rate", m43.get("citation_grounding"), "= 100%"),
        _row("Recommendation accuracy", m43.get("recommendation_accuracy"), "≥ 85%"),
        _row("Hallucination rate (denial cases approved)", m43.get("hallucination_rate"), "< 5%", lower_better=True),
        _row("Latency P50", m43.get("latency_p50_s"), "< 20s", lower_better=True, pct=False),
        "",
        "## Phase 4.4 — PAS Bundle Builder",
        "",
        "| Metric | Result | Target | Gate |",
        "|---|---|---|---|",
        _row("Bundle $validate pass rate", m44.get("validation_pass_rate"), "= 100%"),
        _row("Claim resource present", m44.get("has_claim_rate"), "= 100%"),
        _row("Provenance resource present (audit trail)", m44.get("has_provenance_rate"), "= 100%"),
        _row("Reviewer round-trip latency P50", m44.get("latency_p50_s"), "< 5s", lower_better=True, pct=False),
        "",
        "---",
        "",
        "## Known limitations",
        "",
        "- Policy corpus is limited to CMS NCD 220.6.17 (MRI lumbar spine). Real-world deployment requires ingestion of payer-specific LCDs.",
        "- Synthea-generated patients are synthetic; clinical validity of evidence profiles has not been reviewed by a clinician.",
        "- Bundle $validate runs against HAPI's interpretation of the Da Vinci PAS IG; Inferno test kit validation is a Phase 4.5 stretch goal.",
        "- gpt-4o is used as the Reasoner; other models can be evaluated via `REASONER_MODEL` env var.",
        "",
        "---",
        "",
        "_Generated by `make evals`. See `evals/runners/run_all.py` for details._",
        "",
    ]

    with open(SCORECARD_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ci", action="store_true")
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()

    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"\nPrior-Auth Co-pilot — Combined Eval Runner")
    print(f"Run: {run_ts}\n")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    metrics: dict = {}

    # Phase 4.2
    extra_42 = ["--no-llm"] if args.no_llm else []
    m = _run_phase("4_2", extra_42, "Phase 4.2 — Evidence Retrieval (20 cases)")
    if m:
        metrics["4_2"] = m

    # Phase 4.3
    m = _run_phase("4_3", [], "Phase 4.3 — Medical Necessity Reasoner (30 cases)")
    if m:
        metrics["4_3"] = m

    # Phase 4.4
    m = _run_phase("4_4", [], "Phase 4.4 — PAS Bundle Builder (10 cases)")
    if m:
        metrics["4_4"] = m

    # Combined scorecard
    _write_combined_scorecard(metrics, run_ts)
    print(f"\n{'═' * 60}")
    print(f"  Combined scorecard → {SCORECARD_PATH.relative_to(REPO_ROOT)}")

    # Write combined JSON
    combined_out = RESULTS_DIR / "v1.0-metrics.json"
    with open(combined_out, "w", encoding="utf-8") as fh:
        json.dump({"run_ts": run_ts, "phases": metrics}, fh, indent=2, default=str)
    print(f"  Combined metrics  → {combined_out.relative_to(REPO_ROOT)}")
    print(f"{'═' * 60}\n")

    if args.ci:
        # Check all gates
        m42 = metrics.get("4_2", {}).get("metrics", {})
        m43 = metrics.get("4_3", {}).get("metrics", {})
        m44 = metrics.get("4_4", {}).get("metrics", {})
        gates = [
            m42.get("tool_call_accuracy", 0) >= 0.90,
            m42.get("checklist_recall", 0) >= 1.00,
            m43.get("recommendation_accuracy", 0) >= 0.85,
            m43.get("hallucination_rate", 1) <= 0.05,
            m44.get("validation_pass_rate", 0) >= 1.00,
        ]
        if not all(gates):
            print("CI: one or more eval gates failed — exiting 1.")
            sys.exit(1)


if __name__ == "__main__":
    main()
