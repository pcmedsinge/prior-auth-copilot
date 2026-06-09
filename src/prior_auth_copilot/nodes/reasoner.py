"""
src/prior_auth_copilot/nodes/reasoner.py

Medical Necessity Reasoner node — the core of Phase 4.3.

Process:
  1. Retrieve top-k policy paragraphs relevant to the requested service
     and the patient's evidence profile (via PolicyRetriever).
  2. Call gpt-4o with a structured prompt containing the evidence package
     + retrieved policy chunks → produce a structured Decision JSON.
  3. Run the citation checker: every cited chunk_hash must exist in the
     LanceDB policy store. Hallucinated citations are stripped and logged
     as grounding_issues in the Decision object.

Input  (from PAState): patient_id, service, evidence_package
Output (to PAState):   decision
"""

from __future__ import annotations

import json
import os

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from prior_auth_copilot.rag.retriever import PolicyRetriever
from prior_auth_copilot.state import (
    CriterionResult,
    Decision,
    EvidencePackage,
    PAState,
    ServiceRequest,
)

log = structlog.get_logger(__name__)

REASONER_MODEL = os.getenv("REASONER_MODEL", "gpt-4o")
TOP_K = int(os.getenv("TOP_K_POLICY_CHUNKS", "8"))

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a clinical medical necessity reviewer for a US health payer.

Your task: given a patient's clinical evidence package and a set of policy paragraphs,
determine whether a Prior Authorization request for the specified service is supported.

For EACH policy criterion, output a structured verdict:
  - status: "met" | "not_met" | "unclear"
  - evidence_refs: list of FHIR resource references (e.g. ["Procedure/abc"]) that
    support the verdict. Use ONLY references that appear in the evidence package.
    Do NOT fabricate references.
  - citation: the exact chunk_hash of the policy paragraph you are citing.
    Use ONLY hashes that appear in the POLICY CHUNKS section below.
    Do NOT fabricate hashes.
  - citation_text: a short (≤ 30 word) verbatim excerpt from the cited paragraph.
  - explanation: one sentence explaining your verdict.

Then produce an overall_recommendation:
  - "approve" if all required criteria are met
  - "deny" if one or more required criteria are not met and no red-flag applies
  - "needs_review" if any criterion is "unclear" or evidence is ambiguous

Finally, write a summary: one paragraph in plain English for the utilization
management nurse explaining the reasoning.

IMPORTANT RULES:
1. Never fabricate FHIR resource references. Only use refs from the Evidence Package.
2. Never fabricate policy chunk hashes. Only use hashes from the Policy Chunks section.
3. If evidence is absent for a criterion, set status="not_met" or "unclear" — never invent evidence.
4. Output ONLY valid JSON conforming to the schema. No markdown, no prose outside JSON.

OUTPUT SCHEMA (return exactly this JSON structure):
{
  "overall_recommendation": "approve" | "deny" | "needs_review",
  "criteria": [
    {
      "criterion": "<criterion name>",
      "status": "met" | "not_met" | "unclear",
      "evidence_refs": ["<FHIR ref>", ...],
      "citation": "<chunk_hash>",
      "citation_text": "<verbatim excerpt ≤30 words>",
      "explanation": "<one sentence>"
    }
  ],
  "summary": "<plain-English paragraph for UM nurse>"
}
"""


def _build_user_prompt(
    patient_id: str,
    service: ServiceRequest,
    pkg: EvidencePackage,
    policy_chunks: list,
) -> str:
    """Assemble the user message with evidence + policy context."""

    # Evidence summary
    evidence_lines = [
        f"Patient ID: {patient_id}",
        f"Requested service: {service.service_display} ({service.service_code})",
        f"Payer: {service.payer_id or 'CMS Medicare'}",
        "",
        "--- CHECKLIST SUMMARY ---",
    ]
    for item in pkg.checklist.items:
        status = "✓ MET" if item.met else "✗ NOT MET"
        evidence_lines.append(f"  [{status}] {item.criterion}")
        if item.evidence_refs:
            evidence_lines.append(f"    Evidence refs: {item.evidence_refs}")
        if not item.met and item.note:
            evidence_lines.append(f"    Note: {item.note}")

    evidence_lines += ["", "--- EVIDENCE PACKAGE ---"]
    tagged = [i for i in pkg.items if i.checklist_tags]
    for item in tagged:
        evidence_lines.append(
            f"  [{item.resource_type}] {item.resource_ref} | tags: {item.checklist_tags}"
        )
        if item.why_it_matters:
            evidence_lines.append(f"    Summary: {item.why_it_matters}")

    # Policy chunks
    policy_lines = ["", "--- POLICY CHUNKS ---"]
    for i, chunk in enumerate(policy_chunks, 1):
        policy_lines.append(
            f"\n[Chunk {i}] policy_id={chunk.policy_id} | section={chunk.section}"
        )
        policy_lines.append(f"  chunk_hash={chunk.chunk_hash}")
        policy_lines.append(f"  {chunk.text[:500]}")

    return "\n".join(evidence_lines + policy_lines)


# ---------------------------------------------------------------------------
# Citation checker
# ---------------------------------------------------------------------------


def _check_citations(
    criteria: list[CriterionResult],
    retriever: PolicyRetriever,
) -> tuple[list[CriterionResult], list[str]]:
    """
    Verify every citation hash exists in the policy store.
    Returns (cleaned criteria, list of bad hashes).
    Criteria with bad citations have their citation cleared and status set to "unclear".
    """
    grounding_issues: list[str] = []
    cleaned: list[CriterionResult] = []

    for criterion in criteria:
        if criterion.citation and not retriever.verify_citation(criterion.citation):
            log.warning(
                "citation_check.failed",
                criterion=criterion.criterion,
                bad_hash=criterion.citation,
            )
            grounding_issues.append(criterion.citation)
            # Downgrade to unclear — do not pass a hallucinated citation
            cleaned.append(criterion.model_copy(update={
                "citation": "",
                "citation_text": "[citation removed — hash not found in policy store]",
                "status": "unclear",
            }))
        else:
            cleaned.append(criterion)

    return cleaned, grounding_issues


# ---------------------------------------------------------------------------
# Reasoner node
# ---------------------------------------------------------------------------


def reasoner_node(state: PAState) -> dict:
    """LangGraph node function for the Medical Necessity Reasoner."""

    if state.get("error"):
        return {}

    patient_id: str = state.get("patient_id", "")
    service: ServiceRequest = state.get("service")
    pkg: EvidencePackage | None = state.get("evidence_package")

    if pkg is None:
        return {"error": "Reasoner: evidence_package missing from state. Run Evidence Gatherer first."}

    log.info("reasoner_node.start", patient_id=patient_id, model=REASONER_MODEL)

    # ── Step 1: RAG retrieval ─────────────────────────────────────────────
    retriever = PolicyRetriever()
    service_display = service.service_display if service else "MRI lumbar spine"

    # Build a rich retrieval query from the checklist outcome
    unmet = [i.criterion for i in pkg.checklist.items if not i.met]
    query = (
        f"{service_display} medical necessity criteria coverage determination. "
        + (f"Unmet criteria: {', '.join(unmet)}." if unmet else "")
    )

    try:
        policy_chunks = retriever.retrieve(query, top_k=TOP_K)
    except RuntimeError as exc:
        return {"error": f"Reasoner: policy store error — {exc}"}

    log.info("reasoner_node.retrieved", chunks=len(policy_chunks))

    # ── Step 2: LLM reasoning ─────────────────────────────────────────────
    # model_kwargs used instead of response_format= to avoid LangChain deprecation warning
    llm = ChatOpenAI(
        model=REASONER_MODEL,
        temperature=0,
        model_kwargs={"response_format": {"type": "json_object"}},
    )

    user_msg = _build_user_prompt(patient_id, service, pkg, policy_chunks)

    try:
        response = llm.invoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=user_msg),
        ])
        raw_json = response.content.strip()
        data = json.loads(raw_json)
    except Exception as exc:
        log.error("reasoner_node.llm_error", error=str(exc))
        return {"error": f"Reasoner: LLM call failed — {exc}"}

    # ── Step 3: Parse structured output ──────────────────────────────────
    try:
        criteria = [CriterionResult(**c) for c in data.get("criteria", [])]
        overall = data.get("overall_recommendation", "needs_review")
        summary = data.get("summary", "")
    except Exception as exc:
        log.error("reasoner_node.parse_error", error=str(exc))
        return {"error": f"Reasoner: failed to parse LLM output — {exc}"}

    # ── Step 4: Citation checker ──────────────────────────────────────────
    criteria, grounding_issues = _check_citations(criteria, retriever)
    citation_check_passed = len(grounding_issues) == 0

    if grounding_issues:
        log.warning(
            "reasoner_node.grounding_issues",
            count=len(grounding_issues),
            issues=grounding_issues,
        )
        # If citations were hallucinated, downgrade overall recommendation
        if overall == "approve":
            overall = "needs_review"

    decision = Decision(
        patient_id=patient_id,
        service=service,
        overall_recommendation=overall,
        criteria=criteria,
        summary=summary,
        reasoner_model=REASONER_MODEL,
        citation_check_passed=citation_check_passed,
        grounding_issues=grounding_issues,
    )

    log.info(
        "reasoner_node.complete",
        patient_id=patient_id,
        recommendation=overall,
        met=decision.met_count,
        not_met=decision.not_met_count,
        citation_check_passed=citation_check_passed,
    )

    return {"decision": decision}
