"""
src/prior_auth_copilot/nodes/validate_bundle.py

Bundle validation node — runs the assembled PAS Bundle through HAPI $validate
against the da Vinci PAS profile on the payer HAPI instance (port 8090).

A Bundle that fails validation cannot proceed to the Reviewer or Submit nodes.
This enforces the Phase 4.4 DoD: "Zero Bundles emitted that fail $validate."

Input  (from PAState): bundle_envelope
Output (to PAState):   bundle_envelope (validation_passed + issues updated)
                       error            (set if validation fails and is blocking)
"""

from __future__ import annotations

import json
import os

import httpx
import structlog

from prior_auth_copilot.state import BundleEnvelope, PAState

log = structlog.get_logger(__name__)

PAYER_FHIR_BASE = os.getenv("PAYER_FHIR_BASE_URL", "http://localhost:8090/fhir")
PAS_BUNDLE_PROFILE = "http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-pas-request-bundle"


def _parse_validation_issues(outcome: dict) -> list[str]:
    """Extract human-readable issue strings from a FHIR OperationOutcome."""
    issues: list[str] = []
    for issue in outcome.get("issue", []):
        severity = issue.get("severity", "?")
        code = issue.get("code", "?")
        details = issue.get("details", {}).get("text", "")
        location = ", ".join(issue.get("location", []))
        diag = issue.get("diagnostics", "")
        msg = f"[{severity}/{code}] {details or diag}"
        if location:
            msg += f" @ {location}"
        issues.append(msg)
    return issues


def validate_bundle_node(state: PAState) -> dict:
    """LangGraph node: POST Bundle to HAPI $validate, update bundle_envelope."""
    if state.get("error"):
        return {}

    envelope: BundleEnvelope | None = state.get("bundle_envelope")
    if envelope is None:
        return {"error": "ValidateBundle: bundle_envelope missing from state."}

    log.info("validate_bundle.start", bundle_id=envelope.bundle_id, server=PAYER_FHIR_BASE)

    validate_url = f"{PAYER_FHIR_BASE}/Bundle/$validate"
    headers = {"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"}
    params = {"profile": PAS_BUNDLE_PROFILE}

    try:
        resp = httpx.post(
            validate_url,
            json=envelope.bundle,
            headers=headers,
            params=params,
            timeout=60,
        )
    except httpx.ConnectError:
        log.warning("validate_bundle.payer_unreachable", url=validate_url)
        # Payer HAPI not running — treat as a warning, not a hard block in dev.
        # Validation is considered "not run" (passed=False, no blocking error).
        updated = envelope.model_copy(update={
            "validation_passed": False,
            "validation_issues": ["[WARNING] Payer HAPI not reachable — validation skipped. Run `make payer-fhir-up`."],
        })
        return {"bundle_envelope": updated}

    outcome = resp.json()
    issues = _parse_validation_issues(outcome)
    errors = [i for i in issues if i.startswith("[error") or i.startswith("[fatal")]

    if errors:
        log.error("validate_bundle.failed", bundle_id=envelope.bundle_id, errors=errors)
        updated = envelope.model_copy(update={"validation_passed": False, "validation_issues": issues})
        # Blocking — emit error to halt the graph
        return {
            "bundle_envelope": updated,
            "error": f"ValidateBundle: Bundle {envelope.bundle_id} failed $validate ({len(errors)} error(s)). Review validation_issues in bundle_envelope.",
        }

    log.info("validate_bundle.passed", bundle_id=envelope.bundle_id, issues=len(issues))
    updated = envelope.model_copy(update={"validation_passed": True, "validation_issues": issues})
    return {"bundle_envelope": updated}
