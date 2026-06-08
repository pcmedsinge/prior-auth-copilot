"""
src/prior_auth_copilot/evidence/tools.py

Six evidence-retrieval tools for MRI lumbar spine Prior Authorization.

Each function wraps mcp-fhir's `fhir_search` with PA-specific parameter
defaults and returns a normalised list of FHIR resource dicts (the raw
`entry[].resource` objects from the Bundle).

These functions are called directly by the LangGraph Evidence Gatherer node
(Issue #5).  They are also exposed as MCP tools via the mcp-fhir stdio server
for MCP-protocol clients (Phase 4.5+).

All functions are async — call with `await` or via `asyncio.run()`.
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

# Bootstrap .env so FHIR_BASE_URL etc. are set before mcp-fhir's settings load.
load_dotenv(override=False)

# mcp-fhir's fhir_search reads settings from env at import time.
from mcp_fhir.tools.fhir_search import fhir_search  # noqa: E402

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _resources_from_bundle(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract the resource objects from a FHIR searchset Bundle."""
    return [
        entry["resource"]
        for entry in bundle.get("entry", [])
        if "resource" in entry
    ]


def _base_params(patient_id: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    params: dict[str, str] = {"patient": patient_id, "_count": "50"}
    if extra:
        params.update(extra)
    return params


# ---------------------------------------------------------------------------
# Tool 1 — find_observations
# ---------------------------------------------------------------------------


async def find_observations(
    patient_id: str,
    code: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve Observation resources for a patient.

    Parameters
    ----------
    patient_id : FHIR Patient logical ID
    code       : optional LOINC or SNOMED code filter, e.g. "72514-3"
    date_from  : optional lower bound, ISO-8601 date, e.g. "2023-01-01"
    date_to    : optional upper bound, ISO-8601 date, e.g. "2024-01-01"

    Returns
    -------
    List of raw FHIR Observation resource dicts.
    """
    extra: dict[str, str] = {}
    if code:
        extra["code"] = code
    if date_from:
        extra["date"] = f"ge{date_from}"
    if date_to:
        extra.setdefault("date", "")
        # FHIR allows multiple date params; pass as comma-joined value
        extra["date"] = f"ge{date_from},le{date_to}" if date_from else f"le{date_to}"

    bundle = await fhir_search("Observation", _base_params(patient_id, extra))
    return _resources_from_bundle(bundle)


# ---------------------------------------------------------------------------
# Tool 2 — find_conditions
# ---------------------------------------------------------------------------


async def find_conditions(
    patient_id: str,
    category: str | None = None,
    code: str | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve Condition resources for a patient.

    Parameters
    ----------
    patient_id : FHIR Patient logical ID
    category   : optional FHIR condition category, e.g. "problem-list-item"
    code       : optional SNOMED or ICD-10 code filter

    Returns
    -------
    List of raw FHIR Condition resource dicts.
    """
    extra: dict[str, str] = {}
    if category:
        extra["category"] = category
    if code:
        extra["code"] = code

    bundle = await fhir_search("Condition", _base_params(patient_id, extra))
    return _resources_from_bundle(bundle)


# ---------------------------------------------------------------------------
# Tool 3 — find_procedures
# ---------------------------------------------------------------------------


async def find_procedures(
    patient_id: str,
    code: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve Procedure resources for a patient.

    Parameters
    ----------
    patient_id : FHIR Patient logical ID
    code       : optional SNOMED or CPT code filter, e.g. "36048009" (PT procedure)
    date_from  : optional lower bound ISO-8601 date
    date_to    : optional upper bound ISO-8601 date

    Returns
    -------
    List of raw FHIR Procedure resource dicts.
    """
    extra: dict[str, str] = {}
    if code:
        extra["code"] = code
    if date_from and date_to:
        extra["date"] = f"ge{date_from},le{date_to}"
    elif date_from:
        extra["date"] = f"ge{date_from}"
    elif date_to:
        extra["date"] = f"le{date_to}"

    bundle = await fhir_search("Procedure", _base_params(patient_id, extra))
    return _resources_from_bundle(bundle)


# ---------------------------------------------------------------------------
# Tool 4 — find_medication_history
# ---------------------------------------------------------------------------


async def find_medication_history(
    patient_id: str,
    code: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve MedicationRequest resources for a patient.

    Parameters
    ----------
    patient_id : FHIR Patient logical ID
    code       : optional RxNorm code filter, e.g. "197803" (ibuprofen 400mg)
    status     : optional status filter, e.g. "active", "completed", "stopped"

    Returns
    -------
    List of raw FHIR MedicationRequest resource dicts.
    """
    extra: dict[str, str] = {}
    if code:
        extra["medication.code"] = code
    if status:
        extra["status"] = status

    bundle = await fhir_search("MedicationRequest", _base_params(patient_id, extra))
    return _resources_from_bundle(bundle)


# ---------------------------------------------------------------------------
# Tool 5 — find_imaging_studies
# ---------------------------------------------------------------------------


async def find_imaging_studies(
    patient_id: str,
    modality: str | None = None,
    body_site: str | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve ImagingStudy resources for a patient.

    Parameters
    ----------
    patient_id : FHIR Patient logical ID
    modality   : optional DICOM modality code, e.g. "MR" (MRI), "CT", "XR"
    body_site  : optional SNOMED body site code

    Returns
    -------
    List of raw FHIR ImagingStudy resource dicts.
    """
    extra: dict[str, str] = {}
    if modality:
        extra["modality"] = modality
    if body_site:
        extra["bodysite"] = body_site

    bundle = await fhir_search("ImagingStudy", _base_params(patient_id, extra))
    return _resources_from_bundle(bundle)


# ---------------------------------------------------------------------------
# Tool 6 — find_documents
# ---------------------------------------------------------------------------


async def find_documents(
    patient_id: str,
    doc_type: str | None = None,
    date_from: str | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve DocumentReference resources for a patient.

    Parameters
    ----------
    patient_id : FHIR Patient logical ID
    doc_type   : optional LOINC document type code, e.g. "11488-4" (consult note)
    date_from  : optional lower bound ISO-8601 date

    Returns
    -------
    List of raw FHIR DocumentReference resource dicts.
    """
    extra: dict[str, str] = {}
    if doc_type:
        extra["type"] = doc_type
    if date_from:
        extra["date"] = f"ge{date_from}"

    bundle = await fhir_search("DocumentReference", _base_params(patient_id, extra))
    return _resources_from_bundle(bundle)


# ---------------------------------------------------------------------------
# Tool registry  (used by smoke test and future MCP tool registration)
# ---------------------------------------------------------------------------

EVIDENCE_TOOLS = {
    "find_observations": find_observations,
    "find_conditions": find_conditions,
    "find_procedures": find_procedures,
    "find_medication_history": find_medication_history,
    "find_imaging_studies": find_imaging_studies,
    "find_documents": find_documents,
}
