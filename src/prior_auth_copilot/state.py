"""
src/prior_auth_copilot/state.py

LangGraph graph state + Pydantic domain models for the Prior-Auth Co-pilot.

Architecture (per ADR-0003):
  - PAState           TypedDict  — graph state container (LangGraph-native)
  - EvidenceItem      Pydantic   — one retrieved FHIR resource with PA tags
  - EvidencePackage   Pydantic   — full output of the Evidence Gatherer node
  - ServiceRequest    Pydantic   — the proposed clinical service (MRI, GLP-1, etc.)
  - ToolCall          Pydantic   — audit log of each MCP tool invocation
  - ChecklistResult   Pydantic   — deterministic PA checklist outcome
  - CriterionResult   Pydantic   — Reasoner verdict on one policy criterion (Phase 4.3)
  - Decision          Pydantic   — full Reasoner output (Phase 4.3)
  - BundleEnvelope    Pydantic   — assembled Da Vinci PAS Bundle + validation status (Phase 4.4)
  - ReviewerAction    Pydantic   — HITL reviewer decision (Phase 4.4)
  - SubmitResult      Pydantic   — payer ClaimResponse (Phase 4.4)

Rule: never add raw dict fields to PAState — wrap in a Pydantic model first.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any

from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# ---------------------------------------------------------------------------
# Pydantic leaf models
# ---------------------------------------------------------------------------


class ServiceRequest(BaseModel):
    """The proposed clinical service that needs Prior Authorization."""

    service_code: str = Field(
        description="SNOMED or CPT code for the requested service, e.g. '241615005' (MRI lumbar spine)."
    )
    service_display: str = Field(
        default="",
        description="Human-readable service name, e.g. 'MRI lumbar spine'.",
    )
    payer_id: str = Field(
        default="",
        description="Payer identifier (e.g. plan ID or name) for policy lookup.",
    )


class ToolCall(BaseModel):
    """Audit record of one MCP evidence-tool invocation."""

    tool_name: str
    patient_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    result_count: int = 0
    error: str | None = None


class ChecklistItem(BaseModel):
    """One item in the MRI lumbar spine PA policy checklist."""

    criterion: str = Field(description="Human-readable criterion name.")
    met: bool = Field(description="Whether the criterion is satisfied by retrieved evidence.")
    evidence_refs: list[str] = Field(
        default_factory=list,
        description="FHIR resource references that satisfy this criterion, e.g. ['Procedure/abc'].",
    )
    note: str = Field(default="", description="Short explanatory note.")


class ChecklistResult(BaseModel):
    """Deterministic first-pass PA checklist outcome."""

    checklist_version: str = "mri-lumbar-spine-v1"
    items: list[ChecklistItem] = Field(default_factory=list)

    @property
    def all_met(self) -> bool:
        return all(item.met for item in self.items)

    @property
    def met_count(self) -> int:
        return sum(1 for item in self.items if item.met)


class EvidenceItem(BaseModel):
    """
    One retrieved FHIR resource with PA-relevance tags.

    resource_ref  — FHIR logical reference, e.g. "Condition/abc-123"
    resource_type — FHIR resource type, e.g. "Condition"
    resource      — raw FHIR resource dict (as returned by HAPI)
    relevance     — LLM-assigned 0-1 relevance score (set in second pass)
    why_it_matters— LLM-generated one-line summary (set in second pass)
    checklist_tags— which checklist criteria this resource satisfies
    """

    resource_ref: str
    resource_type: str
    resource: dict[str, Any]
    relevance: float = Field(default=0.0, ge=0.0, le=1.0)
    why_it_matters: str = ""
    checklist_tags: list[str] = Field(default_factory=list)


class EvidencePackage(BaseModel):
    """
    Structured output of the Evidence Gatherer node.
    Consumed by the Medical Necessity Reasoner (Phase 4.3).
    """

    patient_id: str
    service: ServiceRequest
    items: list[EvidenceItem] = Field(default_factory=list)
    checklist: ChecklistResult = Field(default_factory=ChecklistResult)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    gatherer_notes: str = ""

    @property
    def resource_count(self) -> int:
        return len(self.items)


# ---------------------------------------------------------------------------
# Phase 4.3 — Reasoner Pydantic models
# ---------------------------------------------------------------------------


class CriterionResult(BaseModel):
    """
    Reasoner verdict on one policy criterion.

    criterion    — human-readable criterion name (from the policy section)
    status       — "met" | "not_met" | "unclear"
    evidence_refs— FHIR resource refs that support the verdict
    citation     — SHA-256 hash of the policy paragraph cited (verified by citation checker)
    citation_text— snippet of the cited policy paragraph (for display only)
    explanation  — one-sentence explanation of the verdict
    """

    criterion: str
    status: str = Field(pattern="^(met|not_met|unclear)$")
    evidence_refs: list[str] = Field(default_factory=list)
    citation: str = Field(
        default="",
        description="SHA-256 hash of the cited policy chunk. Empty if status=unclear.",
    )
    citation_text: str = Field(default="", description="Display-only policy snippet.")
    explanation: str = ""


class Decision(BaseModel):
    """
    Structured output of the Medical Necessity Reasoner node.
    Consumed by the PAS Bundle Builder (Phase 4.4).
    """

    patient_id: str
    service: ServiceRequest
    overall_recommendation: str = Field(
        pattern="^(approve|deny|needs_review)$",
        description="Overall PA recommendation based on all criterion verdicts.",
    )
    criteria: list[CriterionResult] = Field(default_factory=list)
    summary: str = Field(
        default="",
        description="One-paragraph plain-English necessity argument for the UM nurse.",
    )
    reasoner_model: str = ""
    citation_check_passed: bool = False
    grounding_issues: list[str] = Field(
        default_factory=list,
        description="List of citation hashes that failed the grounding check.",
    )

    @property
    def met_count(self) -> int:
        return sum(1 for c in self.criteria if c.status == "met")

    @property
    def not_met_count(self) -> int:
        return sum(1 for c in self.criteria if c.status == "not_met")


# ---------------------------------------------------------------------------
# Phase 4.4 — Bundle Builder + Reviewer + Submit Pydantic models
# ---------------------------------------------------------------------------


class BundleEnvelope(BaseModel):
    """
    The assembled Da Vinci PAS FHIR Bundle + validation metadata.
    Output of the PAS Bundle Builder node.
    """

    bundle: dict[str, Any] = Field(description="Raw FHIR Bundle (type=collection) dict.")
    bundle_id: str = Field(description="Bundle.id — stable, derived from patient_id + run timestamp.")
    validation_passed: bool = False
    validation_issues: list[str] = Field(default_factory=list)
    checkpoint_id: str = Field(default="", description="LangGraph checkpoint ID stored in Provenance.")
    provenance_ref: str = Field(default="", description="Provenance/<id> ref within the Bundle.")


class ReviewerAction(BaseModel):
    """
    HITL reviewer decision — set by the human via the CLI (ADR-0007).
    Passed back to the graph via LangGraph Command(resume=...).
    """

    action: str = Field(
        pattern="^(approve|edit|send_back)$",
        description="Reviewer choice: approve → submit | edit → re-validate | send_back → replay Reasoner",
    )
    justification_override: str = Field(
        default="",
        description="Edited justification text (only used when action=edit).",
    )
    feedback: str = Field(
        default="",
        description="Structured feedback for the Reasoner (only used when action=send_back).",
    )
    reviewer_id: str = Field(default="human-reviewer")


class SubmitResult(BaseModel):
    """Payer ClaimResponse returned by the mock $submit endpoint."""

    claim_response: dict[str, Any] = Field(description="Raw FHIR ClaimResponse dict.")
    outcome: str = Field(
        pattern="^(queued|complete|error|partial)$",
        description="FHIR ClaimResponse.outcome.",
    )
    disposition: str = Field(default="", description="Human-readable disposition text.")
    payer_reference: str = Field(default="", description="Payer-assigned PA reference number.")


# ---------------------------------------------------------------------------
# PAState — LangGraph graph state container (TypedDict)
# ---------------------------------------------------------------------------
# Rules (per ADR-0003):
#   - Use Annotated[list[T], operator.add] for fields that accumulate across nodes.
#   - Use total=False so nodes only need to return the keys they modify.
#   - Never use raw dict values — wrap in a Pydantic model.


class PAState(TypedDict, total=False):
    """
    Shared state passed between all LangGraph nodes.

    Populated progressively:
      patient_id, service    — set by Intake
      evidence_package       — set by Evidence Gatherer (Phase 4.2)
      decision               — set by Medical Necessity Reasoner (Phase 4.3)
      tool_calls             — accumulated by any node that calls a tool
      error                  — set by any node on failure; checked by conditional edges
    """

    patient_id: str
    service: ServiceRequest

    # Evidence Gatherer output (Phase 4.2)
    evidence_package: EvidencePackage | None

    # Reasoner output (Phase 4.3)
    decision: Decision | None

    # Bundle Builder output (Phase 4.4)
    bundle_envelope: BundleEnvelope | None

    # Reviewer HITL action (Phase 4.4) — set by interrupt resume
    reviewer_action: ReviewerAction | None

    # Submit result (Phase 4.4)
    submit_result: SubmitResult | None

    # Accumulated tool-call audit log (all nodes append here)
    tool_calls: Annotated[list[ToolCall], operator.add]

    # Error flag — any node sets this to short-circuit the graph
    error: str | None
