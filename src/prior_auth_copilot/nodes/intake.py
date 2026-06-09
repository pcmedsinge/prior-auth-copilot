"""
src/prior_auth_copilot/nodes/intake.py

Intake node — validates and forwards {patient_id, service, payer_id}.

Phase 4.2 role: no-op stub that accepts a pre-formed PAState and returns it
unchanged after basic validation.  In Phase 4.3+ this node will parse a
natural-language order, resolve the service code, and look up the payer policy.

Input  (from PAState):  patient_id, service
Output (to PAState):    unchanged (passes through)
Error  (to PAState):    sets error if patient_id or service_code is missing
"""

from __future__ import annotations

import structlog

from prior_auth_copilot.state import PAState

log = structlog.get_logger(__name__)


def intake_node(state: PAState) -> dict:
    """
    LangGraph node function for Intake.

    Returns a partial PAState dict.  LangGraph merges the returned dict into
    the existing state via the TypedDict reducers defined in state.py.
    """
    patient_id = state.get("patient_id", "").strip()
    service = state.get("service")

    log.info("intake_node.start", patient_id=patient_id)

    # Validation
    if not patient_id:
        log.error("intake_node.missing_patient_id")
        return {"error": "Intake: patient_id is required but was not provided."}

    if service is None:
        log.error("intake_node.missing_service")
        return {"error": "Intake: service (ServiceRequest) is required but was not provided."}

    if not service.service_code.strip():
        log.error("intake_node.missing_service_code")
        return {"error": "Intake: service.service_code must not be empty."}

    log.info(
        "intake_node.complete",
        patient_id=patient_id,
        service_code=service.service_code,
        payer_id=service.payer_id,
    )

    # Pass through unchanged — no state mutation in Phase 4.2 Intake.
    return {}
