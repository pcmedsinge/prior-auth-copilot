#!/usr/bin/env python3
"""
scripts/mock_payer.py — FastAPI mock payer PAS $submit endpoint.

Simulates a payer's FHIR-based PA API (CMS-0057 / Da Vinci PAS).
Accepts a Bundle via POST /fhir/Claim/$submit and returns a ClaimResponse.

Usage:
    python scripts/mock_payer.py          # starts on port MOCK_PAYER_PORT (default 8091)
    make mock-payer-up                    # same via Makefile (background)

The mock applies simple logic:
  - If the Bundle contains a Claim resource → outcome = "complete" (approved)
  - If validation flag in request headers indicates failure → outcome = "error"
  - Always returns a preAuthRef (synthetic PA reference number)
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

MOCK_PAYER_PORT = int(os.getenv("MOCK_PAYER_PORT", "8091"))

app = FastAPI(title="Prior-Auth Co-pilot Mock Payer", version="1.0.0")


def _make_claim_response(bundle_id: str, outcome: str, bundle: dict) -> dict:
    patient_ref = "Patient/unknown"
    for entry in bundle.get("entry", []):
        res = entry.get("resource", {})
        if res.get("resourceType") == "Claim":
            patient_ref = res.get("patient", {}).get("reference", patient_ref)
            break

    disposition = (
        "Approved: required documentation of medical necessity received."
        if outcome == "complete"
        else "Denied: documentation insufficient to establish medical necessity."
    )

    return {
        "resourceType": "ClaimResponse",
        "id": f"cr-{bundle_id}",
        "status": "active",
        "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/claim-type", "code": "professional"}]},
        "use": "preauthorization",
        "patient": {"reference": patient_ref},
        "created": datetime.now(timezone.utc).isoformat(),
        "insurer": {"reference": "Organization/payer-org"},
        "request": {"reference": f"Bundle/{bundle_id}"},
        "outcome": outcome,
        "disposition": disposition,
        "preAuthRef": f"PA-{str(uuid.uuid4())[:8].upper()}",
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "mock-payer"}


@app.post("/fhir/Claim/$submit")
async def submit_claim(request: Request):
    body = await request.json()
    bundle_id = body.get("id", str(uuid.uuid4())[:8])

    # Simple approval logic: approve if Bundle has a Claim resource
    has_claim = any(
        e.get("resource", {}).get("resourceType") == "Claim"
        for e in body.get("entry", [])
    )
    outcome = "complete" if has_claim else "error"
    claim_response = _make_claim_response(bundle_id, outcome, body)

    return JSONResponse(content=claim_response, status_code=200)


if __name__ == "__main__":
    print(f"Mock payer starting on port {MOCK_PAYER_PORT} ...")
    uvicorn.run(app, host="0.0.0.0", port=MOCK_PAYER_PORT)
