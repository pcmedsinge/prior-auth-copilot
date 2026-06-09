#!/usr/bin/env python3
"""
demo_e2e.py — full end-to-end Prior Auth Co-pilot demo.

Pipeline:
    Intake → Evidence Gatherer → Reasoner → Bundle Builder →
    Validate Bundle → [REVIEWER PAUSE] → Submit → ClaimResponse

The graph pauses at the Reviewer node. This script collects the reviewer
action via an interactive rich CLI prompt, then resumes the graph.

Usage:
    python scripts/demo_e2e.py <patient_id>
    make demo-e2e PATIENT=<patient_id>

Prerequisites:
    make fhir-up          (provider HAPI on 8082)
    make payer-fhir-up    (payer HAPI on 8090 — optional, graceful fallback)
    make ingest-policies  (LanceDB policy store)
    make load-synthea     (50 patients in HAPI)
    python scripts/mock_payer.py &  (mock payer on 8091 — optional)
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

from langgraph.types import Command  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.prompt import Prompt  # noqa: E402

from prior_auth_copilot.graph import build_graph, get_checkpointer  # noqa: E402
from prior_auth_copilot.state import ReviewerAction, ServiceRequest  # noqa: E402

console = Console()


def _get_patient_id() -> str:
    if len(sys.argv) >= 2:
        return sys.argv[1].strip()
    # Try to auto-pick from manifest
    manifest = REPO_ROOT / "data/synthea-config/manifest.json"
    if manifest.exists():
        import json as _json
        data = _json.load(open(manifest))
        patients = data.get("patients", [])
        complete = [p for p in patients if p.get("path") == "complete"]
        if complete:
            pid = complete[0]["patient_id"]
            console.print(f"[dim]Auto-selected patient from manifest: {pid}[/dim]")
            return pid
    console.print("[red]ERROR[/red]: provide patient_id as argument or run `make load-synthea` first.")
    sys.exit(1)


def main() -> None:
    patient_id = _get_patient_id()

    console.rule("[bold cyan]Prior-Auth Co-pilot — End-to-End Demo[/bold cyan]")
    console.print(f"\n[bold]Patient[/bold]  : {patient_id}")
    console.print(f"[bold]Service[/bold]  : MRI lumbar spine")
    console.print(f"[bold]Model[/bold]    : {os.getenv('REASONER_MODEL', 'gpt-4o')}")
    console.print(f"[bold]FHIR[/bold]     : {os.getenv('FHIR_BASE_URL', 'http://localhost:8082/fhir')}\n")

    initial_state = {
        "patient_id": patient_id,
        "service": ServiceRequest(
            service_code="241615005",
            service_display="MRI lumbar spine",
            payer_id="cms-medicare",
        ),
        "tool_calls": [],
    }

    thread_id = f"pa-{patient_id}"
    config = {"configurable": {"thread_id": thread_id}}

    with get_checkpointer() as saver:
        graph = build_graph(checkpointer=saver)

        # ── Phase 1: run until Reviewer interrupt ─────────────────────────
        console.print("[bold]Running pipeline: Intake → Evidence Gatherer → Reasoner → Bundle Builder → Validate ...[/bold]")
        state = graph.invoke(initial_state, config=config)

        if state.get("error"):
            console.print(f"\n[red]ERROR:[/red] {state['error']}")
            sys.exit(1)

        # ── Phase 2: collect reviewer action ──────────────────────────────
        # The graph paused before the Reviewer node (interrupt_before=["reviewer"]).
        # Collect action here in the demo script (simulates the CLI reviewer).
        console.print("\n[bold yellow]GRAPH PAUSED — Reviewer action required[/bold yellow]\n")

        # Show a concise summary for the reviewer
        decision = state.get("decision")
        envelope = state.get("bundle_envelope")
        if decision:
            console.print(f"[bold]Decision:[/bold] {decision.overall_recommendation.upper()}")
            console.print(f"[bold]Summary:[/bold]  {decision.summary[:120]}...\n")
        if envelope:
            val = "[green]PASSED[/green]" if envelope.validation_passed else "[yellow]NOT RUN[/yellow]"
            console.print(f"[bold]Bundle ID:[/bold] {envelope.bundle_id}  |  [bold]$validate:[/bold] {val}\n")

        console.print("[bold]Choose an action:[/bold]")
        console.print("  [green]approve[/green]    — submit to mock payer")
        console.print("  [yellow]edit[/yellow]       — modify justification")
        console.print("  [red]send_back[/red]  — return to Reasoner\n")

        raw = Prompt.ask("[bold]Action[/bold]", choices=["approve", "edit", "send_back"], default="approve")

        justification_override = ""
        feedback = ""
        if raw == "edit":
            justification_override = Prompt.ask("Enter new justification text")
        elif raw == "send_back":
            feedback = Prompt.ask("Enter feedback for the Reasoner")

        reviewer_action = ReviewerAction(
            action=raw,
            justification_override=justification_override,
            feedback=feedback,
        )

        # ── Phase 3: resume graph ─────────────────────────────────────────
        console.print(f"\n[bold]Resuming graph with action: {raw}[/bold]\n")
        final_state = graph.invoke(Command(resume=reviewer_action), config=config)

        if final_state.get("error"):
            console.print(f"\n[red]ERROR:[/red] {final_state['error']}")
            sys.exit(1)

        # ── Phase 4: show result ───────────────────────────────────────────
        submit_result = final_state.get("submit_result")
        if submit_result:
            console.rule("[bold green]Submission Complete[/bold green]")
            console.print(f"\n[bold]Outcome     :[/bold] {submit_result.outcome.upper()}")
            console.print(f"[bold]Disposition :[/bold] {submit_result.disposition}")
            console.print(f"[bold]PA Reference:[/bold] [bold green]{submit_result.payer_reference}[/bold green]\n")
        else:
            console.print("\n[yellow]Pipeline completed without submission (action was not approve).[/yellow]\n")

        # ── Write JSON output ──────────────────────────────────────────────
        out_dir = REPO_ROOT / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"e2e-{patient_id}.json"
        with open(out_file, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "patient_id": patient_id,
                    "decision": final_state.get("decision", {}).model_dump() if final_state.get("decision") else None,
                    "bundle_id": final_state.get("bundle_envelope", {}).bundle_id if final_state.get("bundle_envelope") else None,
                    "reviewer_action": raw,
                    "submit_result": final_state.get("submit_result", {}).model_dump() if final_state.get("submit_result") else None,
                },
                fh, indent=2, default=str,
            )
        console.print(f"[dim]JSON written → {out_file.relative_to(REPO_ROOT)}[/dim]\n")


if __name__ == "__main__":
    main()
