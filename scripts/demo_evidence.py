#!/usr/bin/env python3
"""
demo_evidence.py â€” run the Evidence Gatherer for a single patient.

Usage:
    python scripts/demo_evidence.py <patient_id>
    make demo-evidence PATIENT=<patient_id>

Prints the structured EvidencePackage to stdout and writes JSON to
out/evidence-<patient_id>.json.

Prerequisites:
    make fhir-up        (HAPI running)
    make load-synthea   (50 patients loaded)
    OPENAI_API_KEY set in .env or environment
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env", override=False)

# Add src/ to path so prior_auth_copilot is importable without pip install -e .
sys.path.insert(0, str(REPO_ROOT / "src"))

from prior_auth_copilot.graph import graph  # noqa: E402
from prior_auth_copilot.state import ServiceRequest  # noqa: E402


def _print_section(title: str) -> None:
    width = 60
    print(f"\n{'â”€' * width}")
    print(f"  {title}")
    print(f"{'â”€' * width}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/demo_evidence.py <patient_id>")
        print("       make demo-evidence PATIENT=<patient_id>")
        sys.exit(1)

    patient_id = sys.argv[1].strip()

    print(f"\nPrior-Auth Co-pilot â€” Evidence Gatherer Demo")
    print(f"Patient : {patient_id}")
    print(f"Service : MRI lumbar spine (SNOMED 241615005)")
    print(f"FHIR    : {os.getenv('FHIR_BASE_URL', 'http://localhost:8082/fhir')}")

    # â”€â”€ Run the graph â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    initial_state = {
        "patient_id": patient_id,
        "service": ServiceRequest(
            service_code="241615005",
            service_display="MRI lumbar spine",
            payer_id="demo-payer",
        ),
        "tool_calls": [],
    }

    print("\nRunning graph: Intake â†’ Evidence Gatherer ...")
    result = graph.invoke(initial_state)

    # â”€â”€ Error check â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if result.get("error"):
        print(f"\nERROR: {result['error']}")
        sys.exit(1)

    pkg = result.get("evidence_package")
    if pkg is None:
        print("\nERROR: evidence_package not set in result state.")
        sys.exit(1)

    # â”€â”€ Print evidence package â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _print_section("PA CHECKLIST")
    for item in pkg.checklist.items:
        status = "âœ“" if item.met else "âœ—"
        print(f"  [{status}] {item.criterion}")
        if not item.met and item.note:
            print(f"       â†’ {item.note}")

    print(f"\n  Overall: {pkg.checklist.met_count}/{len(pkg.checklist.items)} criteria met")
    print(f"  {pkg.gatherer_notes}")

    _print_section(f"EVIDENCE ITEMS ({pkg.resource_count} total)")
    tagged = [i for i in pkg.items if i.checklist_tags]
    untagged = [i for i in pkg.items if not i.checklist_tags]

    print(f"\n  Tagged (PA-relevant): {len(tagged)}")
    for item in tagged:
        tags = ", ".join(item.checklist_tags)
        print(f"\n  [{item.resource_type}] {item.resource_ref}")
        print(f"    Tags   : {tags}")
        print(f"    Summary: {item.why_it_matters or '(no LLM summary)'}")

    print(f"\n  Untagged (not PA-relevant): {len(untagged)}")

    _print_section("TOOL CALLS")
    for tc in pkg.tool_calls:
        status = f"error: {tc.error}" if tc.error else f"{tc.result_count} result(s)"
        print(f"  {tc.tool_name:<30} {status}")

    # â”€â”€ Write JSON output â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    out_dir = REPO_ROOT / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"evidence-{patient_id}.json"

    with open(out_file, "w", encoding="utf-8") as fh:
        json.dump(pkg.model_dump(), fh, indent=2, default=str)

    print(f"\n  JSON written â†’ {out_file.relative_to(REPO_ROOT)}")
    print("\nDone.\n")


if __name__ == "__main__":
    main()

