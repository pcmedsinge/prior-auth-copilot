#!/usr/bin/env python3
"""
demo_reason.py — run the full pipeline (Evidence Gatherer + Reasoner) for one patient.

Usage:
    python scripts/demo_reason.py <patient_id>
    make demo-reason PATIENT=<patient_id>

Prints the structured Decision (necessity argument + criterion verdicts) to stdout
and writes JSON to out/decision-<patient_id>.json.

Prerequisites:
    make fhir-up && make load-synthea   (HAPI + 50 patients)
    make ingest-policies                (LanceDB policy store)
    OPENAI_API_KEY set in .env
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env", override=False)
sys.path.insert(0, str(REPO_ROOT / "src"))

from prior_auth_copilot.graph import graph  # noqa: E402
from prior_auth_copilot.state import ServiceRequest  # noqa: E402

ICONS = {"approve": "✅", "deny": "❌", "needs_review": "⚠️"}
STATUS_ICONS = {"met": "✓", "not_met": "✗", "unclear": "?"}


def _section(title: str) -> None:
    print(f"\n{'─' * 62}\n  {title}\n{'─' * 62}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/demo_reason.py <patient_id>")
        print("       make demo-reason PATIENT=<patient_id>")
        sys.exit(1)

    patient_id = sys.argv[1].strip()

    print(f"\nPrior-Auth Co-pilot — Full Pipeline Demo (Phase 4.3)")
    print(f"Patient  : {patient_id}")
    print(f"Service  : MRI lumbar spine (SNOMED 241615005)")
    print(f"Model    : {os.getenv('REASONER_MODEL', 'gpt-4o')}")
    print(f"FHIR     : {os.getenv('FHIR_BASE_URL', 'http://localhost:8082/fhir')}")

    initial_state = {
        "patient_id": patient_id,
        "service": ServiceRequest(
            service_code="241615005",
            service_display="MRI lumbar spine",
            payer_id="cms-medicare",
        ),
        "tool_calls": [],
    }

    print("\nRunning graph: Intake → Evidence Gatherer → Reasoner ...")
    result = graph.invoke(initial_state)

    if result.get("error"):
        print(f"\nERROR: {result['error']}")
        sys.exit(1)

    pkg = result.get("evidence_package")
    decision = result.get("decision")

    if pkg is None:
        print("\nERROR: evidence_package missing.")
        sys.exit(1)
    if decision is None:
        print("\nERROR: decision missing — Reasoner may have failed.")
        sys.exit(1)

    # ── Evidence summary ───────────────────────────────────────────────────
    _section(f"EVIDENCE CHECKLIST ({pkg.checklist.met_count}/{len(pkg.checklist.items)} met)")
    for item in pkg.checklist.items:
        icon = "✓" if item.met else "✗"
        print(f"  [{icon}] {item.criterion}")
        if not item.met and item.note:
            print(f"       → {item.note}")

    # ── Decision ───────────────────────────────────────────────────────────
    rec_icon = ICONS.get(decision.overall_recommendation, "")
    _section(f"DECISION: {rec_icon} {decision.overall_recommendation.upper()}")

    print(f"\n  Citation check : {'✅ PASSED' if decision.citation_check_passed else '❌ FAILED'}")
    if decision.grounding_issues:
        print(f"  Grounding issues: {decision.grounding_issues}")

    print(f"\n  Criteria ({decision.met_count} met / {decision.not_met_count} not met):")
    for c in decision.criteria:
        icon = STATUS_ICONS.get(c.status, "?")
        print(f"\n  [{icon}] {c.criterion}  [{c.status.upper()}]")
        print(f"      {c.explanation}")
        if c.evidence_refs:
            print(f"      Evidence: {c.evidence_refs}")
        if c.citation_text:
            print(f"      Policy:   \"{c.citation_text}\"")

    _section("NECESSITY ARGUMENT (for UM nurse)")
    print(f"\n  {decision.summary}\n")

    # ── Write JSON ─────────────────────────────────────────────────────────
    out_dir = REPO_ROOT / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"decision-{patient_id}.json"

    with open(out_file, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "evidence_package": pkg.model_dump(),
                "decision": decision.model_dump(),
            },
            fh,
            indent=2,
            default=str,
        )

    print(f"  JSON written → {out_file.relative_to(REPO_ROOT)}\n")


if __name__ == "__main__":
    main()
