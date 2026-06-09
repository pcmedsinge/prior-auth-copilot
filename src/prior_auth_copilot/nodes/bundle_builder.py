"""
src/prior_auth_copilot/nodes/bundle_builder.py

PAS Bundle Builder node — deterministic FHIR Bundle assembly.
NO LLM in this node. The Reasoner's structured Decision contains everything needed.

Produces a FHIR Bundle (type=collection) conforming to the Da Vinci PAS IG:
  - Claim (PAS-profiled)          — the PA request itself
  - Patient                        — from the FHIR server (passed by ref via evidence_package)
  - Coverage                       — synthetic (demo patient has synthetic coverage)
  - Organization (provider)        — synthetic provider org
  - Organization (payer)           — synthetic payer org
  - Practitioner                   — synthetic ordering provider
  - Supporting resources (Condition, Procedure, MedicationRequest, Observation)
    — taken directly from the EvidencePackage (FHIR refs preserved)
  - Provenance                     — links Bundle to the LangGraph checkpoint + agent run

The Bundle ID is derived from patient_id + ISO timestamp for auditability.

Input  (from PAState): patient_id, service, evidence_package, decision
Output (to PAState):   bundle_envelope
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from prior_auth_copilot.state import (
    BundleEnvelope,
    Decision,
    EvidencePackage,
    PAState,
    ServiceRequest,
)

log = structlog.get_logger(__name__)

# Da Vinci PAS profile URLs
_PAS_CLAIM_PROFILE = "http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-claim"
_PAS_BUNDLE_PROFILE = "http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-pas-request-bundle"
_US_CORE_PATIENT_PROFILE = "http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient"

# CPT code for MRI lumbar spine without contrast
_MRI_LUMBAR_CPT = "72148"


# ---------------------------------------------------------------------------
# FHIR resource builders
# ---------------------------------------------------------------------------


def _synthetic_patient_ref(patient_id: str) -> dict:
    return {"reference": f"Patient/{patient_id}"}


def _synthetic_coverage(patient_id: str, payer_id: str) -> dict:
    return {
        "resourceType": "Coverage",
        "id": f"coverage-{patient_id[:8]}",
        "status": "active",
        "beneficiary": {"reference": f"Patient/{patient_id}"},
        "payor": [{"reference": "Organization/payer-org"}],
        "class": [{"type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/coverage-class", "code": "plan"}]}, "value": payer_id or "DEMO-PLAN-001"}],
    }


def _synthetic_provider_org() -> dict:
    return {
        "resourceType": "Organization",
        "id": "provider-org",
        "meta": {"profile": ["http://hl7.org/fhir/us/core/StructureDefinition/us-core-organization"]},
        "active": True,
        "name": "Demo Healthcare Provider",
        "identifier": [{"system": "http://hl7.org/fhir/sid/us-npi", "value": "1234567890"}],
    }


def _synthetic_payer_org(payer_id: str) -> dict:
    return {
        "resourceType": "Organization",
        "id": "payer-org",
        "active": True,
        "name": payer_id or "CMS Medicare",
        "identifier": [{"system": "http://hl7.org/fhir/sid/us-npi", "value": "0987654321"}],
    }


def _synthetic_practitioner(patient_id: str) -> dict:
    return {
        "resourceType": "Practitioner",
        "id": f"practitioner-{patient_id[:8]}",
        "meta": {"profile": ["http://hl7.org/fhir/us/core/StructureDefinition/us-core-practitioner"]},
        "active": True,
        "name": [{"family": "Smith", "given": ["Jane"], "prefix": ["Dr."]}],
        "identifier": [{"system": "http://hl7.org/fhir/sid/us-npi", "value": "1122334455"}],
    }


def _build_claim(
    patient_id: str,
    service: ServiceRequest,
    decision: Decision,
    bundle_id: str,
) -> dict:
    """Build the PAS-profiled Claim resource."""
    now_iso = datetime.now(timezone.utc).isoformat()

    # Supporting info items — one per met criterion with evidence refs
    supporting_info = []
    for i, criterion in enumerate(decision.criteria):
        if criterion.status == "met" and criterion.evidence_refs:
            supporting_info.append({
                "sequence": i + 1,
                "category": {
                    "coding": [{
                        "system": "http://hl7.org/fhir/us/davinci-pas/CodeSystem/PASSupportingInfoType",
                        "code": "patientEvent",
                    }]
                },
                "valueReference": {"reference": criterion.evidence_refs[0]},
            })

    return {
        "resourceType": "Claim",
        "id": f"claim-{bundle_id}",
        "meta": {"profile": [_PAS_CLAIM_PROFILE]},
        "status": "active",
        "type": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/claim-type", "code": "professional"}]
        },
        "use": "preauthorization",
        "patient": _synthetic_patient_ref(patient_id),
        "created": now_iso,
        "insurer": {"reference": "Organization/payer-org"},
        "provider": {"reference": "Organization/provider-org"},
        "priority": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/processpriority", "code": "normal"}]
        },
        "careTeam": [{"sequence": 1, "provider": {"reference": f"Practitioner/practitioner-{patient_id[:8]}"}}],
        "supportingInfo": supporting_info,
        "diagnosis": [],
        "insurance": [{"sequence": 1, "focal": True, "coverage": {"reference": f"Coverage/coverage-{patient_id[:8]}"}}],
        "item": [{
            "sequence": 1,
            "careTeamSequence": [1],
            "productOrService": {
                "coding": [{"system": "http://www.ama-assn.org/go/cpt", "code": _MRI_LUMBAR_CPT,
                             "display": "MRI lumbar spine without contrast"}]
            },
            "servicedDate": datetime.now(timezone.utc).date().isoformat(),
            "quantity": {"value": 1},
            "extension": [{
                "url": "http://hl7.org/fhir/us/davinci-pas/StructureDefinition/extension-serviceItemRequestType",
                "valueCodeableConcept": {
                    "coding": [{"system": "http://codesystems.fhir.us/davinci-pas/PAServiceRequestType", "code": "initial"}]
                }
            }],
        }],
    }


def _build_provenance(
    bundle_id: str,
    patient_id: str,
    checkpoint_id: str,
) -> dict:
    """Build a Provenance resource linking the Bundle to the agent run."""
    return {
        "resourceType": "Provenance",
        "id": f"provenance-{bundle_id}",
        "target": [{"reference": f"Bundle/{bundle_id}"}],
        "recorded": datetime.now(timezone.utc).isoformat(),
        "agent": [{
            "type": {
                "coding": [{"system": "http://terminology.hl7.org/CodeSystem/provenance-participant-type",
                             "code": "author"}]
            },
            "who": {"display": "prior-auth-copilot LangGraph agent"},
        }],
        "extension": [{
            "url": "https://github.com/pcmedsinge/prior-auth-copilot/StructureDefinition/agent-checkpoint-id",
            "valueString": checkpoint_id or "no-checkpoint",
        }],
    }


# ---------------------------------------------------------------------------
# Bundle assembly
# ---------------------------------------------------------------------------


def _assemble_bundle(
    patient_id: str,
    service: ServiceRequest,
    pkg: EvidencePackage,
    decision: Decision,
    checkpoint_id: str,
) -> dict[str, Any]:
    """Assemble the full Da Vinci PAS request Bundle."""
    now_iso = datetime.now(timezone.utc).isoformat()
    bundle_id = hashlib.sha256(f"{patient_id}-{now_iso}".encode()).hexdigest()[:16]

    claim = _build_claim(patient_id, service, decision, bundle_id)
    coverage = _synthetic_coverage(patient_id, service.payer_id)
    provider_org = _synthetic_provider_org()
    payer_org = _synthetic_payer_org(service.payer_id)
    practitioner = _synthetic_practitioner(patient_id)
    provenance = _build_provenance(bundle_id, patient_id, checkpoint_id)

    # Supporting clinical resources — take from evidence package (PA-relevant items only)
    supporting_resources = [
        item.resource for item in pkg.items
        if item.checklist_tags and item.resource.get("id")
    ]

    entries = [
        {"fullUrl": f"urn:uuid:{claim['id']}", "resource": claim},
        {"fullUrl": f"urn:uuid:{coverage['id']}", "resource": coverage},
        {"fullUrl": f"urn:uuid:{provider_org['id']}", "resource": provider_org},
        {"fullUrl": f"urn:uuid:{payer_org['id']}", "resource": payer_org},
        {"fullUrl": f"urn:uuid:{practitioner['id']}", "resource": practitioner},
        {"fullUrl": f"urn:uuid:{provenance['id']}", "resource": provenance},
    ]
    for res in supporting_resources:
        rtype = res.get("resourceType", "Resource")
        rid = res.get("id", str(uuid.uuid4()))
        entries.append({"fullUrl": f"urn:uuid:{rid}", "resource": res})

    return {
        "resourceType": "Bundle",
        "id": bundle_id,
        "meta": {"profile": [_PAS_BUNDLE_PROFILE]},
        "type": "collection",
        "timestamp": now_iso,
        "entry": entries,
    }


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------


def bundle_builder_node(state: PAState) -> dict:
    """LangGraph node for the PAS Bundle Builder."""
    if state.get("error"):
        return {}

    patient_id = state.get("patient_id", "")
    service: ServiceRequest = state.get("service")
    pkg: EvidencePackage = state.get("evidence_package")
    decision: Decision = state.get("decision")

    if pkg is None or decision is None:
        return {"error": "BundleBuilder: evidence_package and decision are required."}

    log.info("bundle_builder.start", patient_id=patient_id)

    # Retrieve checkpoint_id if available in state (set by the graph's checkpointer)
    checkpoint_id = state.get("_metadata", {}).get("checkpoint_id", "") if hasattr(state, "get") else ""

    bundle = _assemble_bundle(patient_id, service, pkg, decision, checkpoint_id)
    bundle_id = bundle["id"]
    provenance_ref = f"Provenance/provenance-{bundle_id}"

    envelope = BundleEnvelope(
        bundle=bundle,
        bundle_id=bundle_id,
        validation_passed=False,  # will be set by the validate step
        checkpoint_id=checkpoint_id,
        provenance_ref=provenance_ref,
    )

    log.info("bundle_builder.complete", bundle_id=bundle_id, entries=len(bundle["entry"]))
    return {"bundle_envelope": envelope}
