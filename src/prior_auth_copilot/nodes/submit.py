"""
src/prior_auth_copilot/nodes/submit.py

Submit node — POSTs the validated PAS Bundle to the mock payer $submit endpoint.
Only callable if the Reviewer approved (enforced by the graph's conditional edge).

Returns a SubmitResult containing the mock ClaimResponse.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import httpx
import structlog

from prior_auth_copilot.state import (
    BundleEnvelope,
    PAState,
    ReviewerAction,
    SubmitResult,
)

log = structlog.get_logger(__name__)

MOCK_PAYER_PORT = int(os.getenv("MOCK_PAYER_PORT", "8091"))
MOCK_PAYER_URL = f"http://localhost:{MOCK_PAYER_PORT}"


def _synthetic_claim_response(bundle_id: str, outcome: str) -> dict:
    """Generate a synthetic FHIR ClaimResponse."""
    now_iso = datetime.now(timezone.utc).isoformat()
    disposition = "Approved: medical necessity criteria met." if outcome == "complete" else "Denied: insufficient documentation."
    return {
        "resourceType": "ClaimResponse",
        "id": f"cr-{bundle_id}",
        "status": "active",
        "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/claim-type", "code": "professional"}]},
        "use": "preauthorization",
        "patient": {"reference": "Patient/unknown"},
        "created": now_iso,
        "insurer": {"reference": "Organization/payer-org"},
        "request": {"reference": f"Bundle/{bundle_id}"},
        "outcome": outcome,
        "disposition": disposition,
        "preAuthRef": f"PA-{str(uuid.uuid4())[:8].upper()}",
    }


def submit_node(state: PAState) -> dict:
    """LangGraph node: submit the Bundle to the mock payer."""
    if state.get("error"):
        return {}

    reviewer_action: ReviewerAction | None = state.get("reviewer_action")
    envelope: BundleEnvelope | None = state.get("bundle_envelope")

    if reviewer_action is None or reviewer_action.action != "approve":
        return {"error": "Submit: reviewer must approve before submission."}

    if envelope is None:
        return {"error": "Submit: bundle_envelope missing."}

    log.info("submit_node.start", bundle_id=envelope.bundle_id, payer=MOCK_PAYER_URL)

    # Try the FastAPI mock_payer.py server first; fall back to synthetic response if not running.
    try:
        resp = httpx.post(
            f"{MOCK_PAYER_URL}/fhir/Claim/$submit",
            json=envelope.bundle,
            headers={"Content-Type": "application/fhir+json"},
            timeout=30,
        )
        claim_response = resp.json()
        outcome = claim_response.get("outcome", "complete")
        payer_ref = claim_response.get("preAuthRef", "")
    except httpx.ConnectError:
        log.warning("submit_node.mock_payer_unreachable", url=MOCK_PAYER_URL)
        # Graceful fallback — synthesise a ClaimResponse for demo
        outcome = "complete" if envelope.validation_passed else "error"
        claim_response = _synthetic_claim_response(envelope.bundle_id, outcome)
        payer_ref = claim_response.get("preAuthRef", "")

    disposition = claim_response.get("disposition", "")
    log.info("submit_node.complete", bundle_id=envelope.bundle_id, outcome=outcome, payer_ref=payer_ref)

    return {
        "submit_result": SubmitResult(
            claim_response=claim_response,
            outcome=outcome,
            disposition=disposition,
            payer_reference=payer_ref,
        )
    }
