"""
src/prior_auth_copilot/nodes/evidence_gatherer.py

Evidence Gatherer node — assembles the clinical evidence package for an MRI
lumbar spine Prior Authorization request.

Two-pass approach (per Phase 4.2 spec):
  Pass 1 — Deterministic checklist tagger
    Calls all 6 evidence tools, tags each retrieved resource against a
    hardcoded MRI-lumbar-spine PA policy checklist.

  Pass 2 — LLM summarisation (gpt-4o-mini)
    For each resource that matches at least one checklist criterion, asks the
    LLM to produce a one-line "why this matters" explanation.
    Resources with no checklist tags are included but left unsummarised.

Input  (from PAState): patient_id, service
Output (to PAState):   evidence_package, tool_calls
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Any

import structlog
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from prior_auth_copilot.evidence.tools import (
    find_conditions,
    find_documents,
    find_imaging_studies,
    find_medication_history,
    find_observations,
    find_procedures,
)
from prior_auth_copilot.state import (
    ChecklistItem,
    ChecklistResult,
    EvidenceItem,
    EvidencePackage,
    PAState,
    ToolCall,
)

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# PA checklist codes (must match the GMF module in data/synthea-config/modules/)
# ---------------------------------------------------------------------------

_SNOMED_LOW_BACK_PAIN = "279039007"
_SNOMED_RADICULOPATHY = "57054005"
_SNOMED_PT_PROCEDURE = "36048009"
_RXNORM_IBUPROFEN = "197803"
_LOINC_PAIN_SCORE = "72514-3"

# Minimum gap between PT sessions to count as "≥6 weeks conservative therapy"
_PT_GAP_DAYS = 28


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _codings(resource: dict[str, Any]) -> list[dict[str, Any]]:
    return resource.get("code", {}).get("coding", [])


def _has_code(resource: dict[str, Any], system_fragment: str, code: str) -> bool:
    for c in _codings(resource):
        if system_fragment.lower() in c.get("system", "").lower() and c.get("code") == code:
            return True
    return False


def _fhir_ref(resource: dict[str, Any]) -> str:
    rtype = resource.get("resourceType", "Resource")
    rid = resource.get("id", "unknown")
    return f"{rtype}/{rid}"


def _pt_dates(procedures: list[dict[str, Any]]) -> list[datetime]:
    dates: list[datetime] = []
    for proc in procedures:
        if _has_code(proc, "snomed", _SNOMED_PT_PROCEDURE):
            raw = (
                proc.get("performedPeriod", {}).get("start")
                or proc.get("performedDateTime", "")
            )
            if raw:
                try:
                    dates.append(datetime.fromisoformat(raw[:10]))
                except ValueError:
                    pass
    return sorted(dates)


# ---------------------------------------------------------------------------
# Pass 1 — deterministic checklist tagger
# ---------------------------------------------------------------------------


def _build_checklist(
    conditions: list[dict],
    procedures: list[dict],
    medications: list[dict],
    observations: list[dict],
) -> tuple[ChecklistResult, dict[str, list[str]]]:
    """
    Evaluate the MRI lumbar spine PA checklist.

    Returns:
        ChecklistResult — pass/fail per criterion
        tags_map        — {resource_ref: [criterion_name, ...]} for tagging EvidenceItems
    """
    tags_map: dict[str, list[str]] = {}

    def _tag(resource: dict, criterion: str) -> None:
        ref = _fhir_ref(resource)
        tags_map.setdefault(ref, []).append(criterion)

    # ── Criterion 1: LBP diagnosis on record ──────────────────────────────
    lbp_resources = [c for c in conditions if _has_code(c, "snomed", _SNOMED_LOW_BACK_PAIN)]
    for r in lbp_resources:
        _tag(r, "lbp_diagnosis")
    c1 = ChecklistItem(
        criterion="Low back pain diagnosis on record",
        met=bool(lbp_resources),
        evidence_refs=[_fhir_ref(r) for r in lbp_resources],
        note="SNOMED 279039007 required" if not lbp_resources else "",
    )

    # ── Criterion 2: NSAID prescribed ────────────────────────────────────
    nsaid_resources = [m for m in medications if _has_code(m, "rxnorm", _RXNORM_IBUPROFEN)]
    for r in nsaid_resources:
        _tag(r, "nsaid_prescribed")
    c2 = ChecklistItem(
        criterion="NSAID prescribed (conservative pharmacotherapy)",
        met=bool(nsaid_resources),
        evidence_refs=[_fhir_ref(r) for r in nsaid_resources],
        note="RxNorm 197803 (ibuprofen) required" if not nsaid_resources else "",
    )

    # ── Criterion 3: PT ≥2 sessions ≥28 days apart ────────────────────────
    pt_dates = _pt_dates(procedures)
    pt_threshold_met = (
        len(pt_dates) >= 2 and (pt_dates[-1] - pt_dates[0]).days >= _PT_GAP_DAYS
    )
    pt_resources = [p for p in procedures if _has_code(p, "snomed", _SNOMED_PT_PROCEDURE)]
    for r in pt_resources:
        _tag(r, "physical_therapy")
    gap_days = (pt_dates[-1] - pt_dates[0]).days if len(pt_dates) >= 2 else 0
    c3 = ChecklistItem(
        criterion="Physical therapy ≥2 sessions with ≥28-day gap (failed conservative therapy)",
        met=pt_threshold_met,
        evidence_refs=[_fhir_ref(r) for r in pt_resources],
        note=(
            ""
            if pt_threshold_met
            else f"{len(pt_dates)} PT session(s) found; gap = {gap_days} days (need ≥28)"
        ),
    )

    # ── Criterion 4: Pain score documented ────────────────────────────────
    pain_resources = [o for o in observations if _has_code(o, "loinc", _LOINC_PAIN_SCORE)]
    for r in pain_resources:
        _tag(r, "pain_score")
    c4 = ChecklistItem(
        criterion="Pain severity score documented (LOINC 72514-3)",
        met=bool(pain_resources),
        evidence_refs=[_fhir_ref(r) for r in pain_resources],
        note="LOINC 72514-3 required" if not pain_resources else "",
    )

    # ── Criterion 5 (bonus): Radiculopathy / neurological deficit ────────
    neuro_resources = [c for c in conditions if _has_code(c, "snomed", _SNOMED_RADICULOPATHY)]
    for r in neuro_resources:
        _tag(r, "neurological_deficit")
    c5 = ChecklistItem(
        criterion="Neurological deficit (radiculopathy) documented — strengthens PA case",
        met=bool(neuro_resources),
        evidence_refs=[_fhir_ref(r) for r in neuro_resources],
        note="Optional but significantly improves PA approval odds",
    )

    checklist = ChecklistResult(items=[c1, c2, c3, c4, c5])
    return checklist, tags_map


# ---------------------------------------------------------------------------
# Pass 2 — LLM summarisation
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a clinical documentation assistant helping a utilization-management nurse \
prepare a Prior Authorization evidence package for an MRI of the lumbar spine.

Given one FHIR resource and the patient's clinical context, write exactly ONE sentence \
(≤ 25 words) explaining why this resource is relevant to the PA request.

Rules:
- Be specific: mention the resource type and the clinical fact it proves.
- Do NOT fabricate any dates, codes, or values not in the resource JSON.
- If the resource is clearly irrelevant, respond with exactly: "Not directly relevant."
"""


def _llm_summarise_batch(
    items: list[EvidenceItem],
    patient_id: str,
    service_display: str,
) -> list[EvidenceItem]:
    """
    Call gpt-4o-mini once per tagged EvidenceItem to produce why_it_matters.
    Untagged items (no checklist_tags) are skipped to save cost.
    """
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    llm = ChatOpenAI(model=model_name, temperature=0)

    updated: list[EvidenceItem] = []
    for item in items:
        if not item.checklist_tags:
            # Not relevant to any checklist criterion — skip LLM call
            updated.append(item)
            continue

        resource_json = str(item.resource)[:800]  # truncate to avoid token bloat
        user_msg = (
            f"Patient: {patient_id}\n"
            f"Requested service: {service_display}\n"
            f"PA checklist tags: {', '.join(item.checklist_tags)}\n\n"
            f"FHIR resource (truncated):\n{resource_json}"
        )

        try:
            response = llm.invoke(
                [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_msg)]
            )
            summary = response.content.strip()
            relevance = 0.0 if summary == "Not directly relevant." else 0.8
            updated.append(
                item.model_copy(
                    update={"why_it_matters": summary, "relevance": relevance}
                )
            )
        except Exception as exc:
            log.warning("llm_summarise.error", ref=item.resource_ref, error=str(exc))
            updated.append(
                item.model_copy(
                    update={
                        "why_it_matters": f"[LLM error: {exc}]",
                        "relevance": 0.5,
                    }
                )
            )

    return updated


# ---------------------------------------------------------------------------
# Main node function
# ---------------------------------------------------------------------------


async def _gather_evidence_async(patient_id: str) -> tuple[
    list[dict], list[dict], list[dict], list[dict], list[dict], list[dict], list[ToolCall]
]:
    """Run all 6 tool calls concurrently and return results + audit log."""
    tool_calls: list[ToolCall] = []

    async def _call(name: str, coro):
        try:
            result = await coro
            tool_calls.append(ToolCall(tool_name=name, patient_id=patient_id, result_count=len(result)))
            return result
        except Exception as exc:
            log.error("evidence_tool.error", tool=name, error=str(exc))
            tool_calls.append(ToolCall(tool_name=name, patient_id=patient_id, error=str(exc)))
            return []

    (
        conditions,
        procedures,
        medications,
        observations,
        imaging,
        documents,
    ) = await asyncio.gather(
        _call("find_conditions", find_conditions(patient_id)),
        _call("find_procedures", find_procedures(patient_id)),
        _call("find_medication_history", find_medication_history(patient_id)),
        _call("find_observations", find_observations(patient_id)),
        _call("find_imaging_studies", find_imaging_studies(patient_id)),
        _call("find_documents", find_documents(patient_id)),
    )
    return conditions, procedures, medications, observations, imaging, documents, tool_calls


def evidence_gatherer_node(state: PAState) -> dict:
    """
    LangGraph node function for Evidence Gatherer.
    Synchronous wrapper around the async gather logic.
    """
    patient_id: str = state.get("patient_id", "")
    service = state.get("service")

    if state.get("error"):
        return {}  # abort if upstream node set an error

    log.info("evidence_gatherer.start", patient_id=patient_id)

    # ── Async tool calls ──────────────────────────────────────────────────
    (
        conditions, procedures, medications,
        observations, imaging, documents,
        tool_calls,
    ) = asyncio.run(_gather_evidence_async(patient_id))

    log.info(
        "evidence_gatherer.tools_done",
        conditions=len(conditions),
        procedures=len(procedures),
        medications=len(medications),
        observations=len(observations),
        imaging=len(imaging),
        documents=len(documents),
    )

    # ── Pass 1: deterministic checklist ───────────────────────────────────
    checklist, tags_map = _build_checklist(conditions, procedures, medications, observations)

    # ── Build EvidenceItem list ───────────────────────────────────────────
    all_resources = conditions + procedures + medications + observations + imaging + documents
    items: list[EvidenceItem] = []
    for resource in all_resources:
        ref = _fhir_ref(resource)
        items.append(
            EvidenceItem(
                resource_ref=ref,
                resource_type=resource.get("resourceType", "Unknown"),
                resource=resource,
                checklist_tags=tags_map.get(ref, []),
            )
        )

    # ── Pass 2: LLM summarisation ─────────────────────────────────────────
    service_display = service.service_display if service else "MRI lumbar spine"
    items = _llm_summarise_batch(items, patient_id, service_display)

    # ── Assemble EvidencePackage ──────────────────────────────────────────
    evidence_package = EvidencePackage(
        patient_id=patient_id,
        service=service or {},  # type: ignore[arg-type]
        items=items,
        checklist=checklist,
        tool_calls=tool_calls,
        gatherer_notes=(
            f"Checklist: {checklist.met_count}/{len(checklist.items)} criteria met. "
            + ("PA approval likely." if checklist.all_met else "PA denial risk — review missing criteria.")
        ),
    )

    log.info(
        "evidence_gatherer.complete",
        patient_id=patient_id,
        items=len(items),
        checklist_all_met=checklist.all_met,
        met_count=checklist.met_count,
    )

    return {
        "evidence_package": evidence_package,
        "tool_calls": tool_calls,
    }
