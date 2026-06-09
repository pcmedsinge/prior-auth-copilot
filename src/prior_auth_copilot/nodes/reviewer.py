"""
src/prior_auth_copilot/nodes/reviewer.py

Reviewer HITL node — LangGraph interrupt() checkpoint + rich CLI.

The graph pauses here. The human reviewer reads the draft Bundle summary and
Decision, then chooses one of three actions:

  approve    → resume graph → submit to mock payer
  edit       → modify justification text → re-validate Bundle → resume
  send_back  → write feedback → replay Reasoner (graph restarts from Reasoner)

The reviewer action is passed back to the graph via:
  graph.invoke(Command(resume=ReviewerAction(...)), config={"thread_id": ...})

Input  (from PAState): patient_id, service, evidence_package, decision, bundle_envelope
Output (to PAState):   reviewer_action  (set when graph resumes)
"""

from __future__ import annotations

from langgraph.types import interrupt

import structlog
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt

from prior_auth_copilot.state import (
    BundleEnvelope,
    Decision,
    EvidencePackage,
    PAState,
    ReviewerAction,
)

log = structlog.get_logger(__name__)
console = Console()

ICONS = {"approve": "✅", "deny": "❌", "needs_review": "⚠️"}
STATUS_ICONS = {"met": "[green]✓[/green]", "not_met": "[red]✗[/red]", "unclear": "[yellow]?[/yellow]"}


def _render_decision(decision: Decision) -> None:
    """Print the Reasoner Decision as a rich Panel."""
    rec_icon = ICONS.get(decision.overall_recommendation, "")
    table = Table(show_header=True, header_style="bold blue", box=None)
    table.add_column("Criterion", style="dim", width=45)
    table.add_column("Status", width=12)
    table.add_column("Evidence", width=30)

    for c in decision.criteria:
        icon = STATUS_ICONS.get(c.status, "?")
        refs = ", ".join(c.evidence_refs[:2]) or "—"
        table.add_row(c.criterion[:44], f"{icon} {c.status}", refs[:29])

    console.print(Panel(
        table,
        title=f"[bold]Reasoner Decision[/bold] — {rec_icon} [bold]{decision.overall_recommendation.upper()}[/bold]",
        border_style="blue",
        padding=(1, 2),
    ))
    console.print(f"\n[bold]Necessity argument:[/bold]\n  {decision.summary}\n")


def _render_bundle_summary(envelope: BundleEnvelope) -> None:
    """Print a summary of the assembled Bundle."""
    entries = envelope.bundle.get("entry", [])
    entry_types = [e.get("resource", {}).get("resourceType", "?") for e in entries]
    val_status = "[green]PASSED[/green]" if envelope.validation_passed else "[yellow]NOT RUN / FAILED[/yellow]"
    issues = envelope.validation_issues

    content = (
        f"Bundle ID   : [bold]{envelope.bundle_id}[/bold]\n"
        f"Entries     : {len(entries)} ({', '.join(entry_types[:6])}{'…' if len(entry_types) > 6 else ''})\n"
        f"$validate   : {val_status}\n"
    )
    if issues:
        content += f"Issues      : {len(issues)} ({issues[0][:60]}{'…' if len(issues) > 1 else ''})\n"

    console.print(Panel(content, title="[bold]Draft PAS Bundle[/bold]", border_style="green", padding=(1, 2)))


def _render_checklist(pkg: EvidencePackage) -> None:
    """Print the evidence checklist."""
    lines = []
    for item in pkg.checklist.items:
        icon = "[green]✓[/green]" if item.met else "[red]✗[/red]"
        lines.append(f"  {icon}  {item.criterion}")
    console.print(Panel("\n".join(lines), title="[bold]Evidence Checklist[/bold]", border_style="yellow", padding=(1, 2)))


def reviewer_node(state: PAState) -> dict:
    """
    LangGraph node for the HITL Reviewer.
    Calls interrupt() to pause the graph and collect the reviewer action.
    """
    if state.get("error"):
        return {}

    patient_id = state.get("patient_id", "")
    decision: Decision | None = state.get("decision")
    envelope: BundleEnvelope | None = state.get("bundle_envelope")
    pkg: EvidencePackage | None = state.get("evidence_package")

    if decision is None or envelope is None or pkg is None:
        return {"error": "Reviewer: decision, bundle_envelope, and evidence_package are required."}

    log.info("reviewer_node.interrupt", patient_id=patient_id)

    # ── Display review panel ───────────────────────────────────────────────
    console.rule("[bold cyan]Prior-Auth Co-pilot — Reviewer[/bold cyan]")
    console.print(f"\n[bold]Patient:[/bold] {patient_id}  |  "
                  f"[bold]Service:[/bold] {state.get('service', {}).service_display if state.get('service') else 'MRI lumbar spine'}\n")

    _render_checklist(pkg)
    _render_decision(decision)
    _render_bundle_summary(envelope)

    console.print("[bold]Choose an action:[/bold]")
    console.print("  [green]approve[/green]    — submit the Bundle to the mock payer")
    console.print("  [yellow]edit[/yellow]       — modify the justification text and re-validate")
    console.print("  [red]send_back[/red]  — return to Reasoner with feedback\n")

    # ── Interrupt: pause graph, collect action from human ─────────────────
    # interrupt() serialises the current state to the SQLite checkpoint and
    # halts execution.  Execution resumes when the caller calls:
    #   graph.invoke(Command(resume=ReviewerAction(...)), config={"thread_id": ...})
    raw_action = interrupt({
        "prompt": "Enter action (approve / edit / send_back): ",
        "patient_id": patient_id,
        "bundle_id": envelope.bundle_id,
    })

    # ── Process resumed action ─────────────────────────────────────────────
    # raw_action is the value passed to Command(resume=...)
    if isinstance(raw_action, ReviewerAction):
        action = raw_action
    elif isinstance(raw_action, dict):
        action = ReviewerAction(**raw_action)
    else:
        action = ReviewerAction(action=str(raw_action).strip().lower() or "approve")

    log.info("reviewer_node.complete", action=action.action, patient_id=patient_id)
    console.print(f"\n[bold]Reviewer action:[/bold] {action.action}\n")

    return {"reviewer_action": action}
