#!/usr/bin/env python3
"""
smoke_mcp_tools.py — verify all 6 evidence-retrieval tools work against HAPI.

Picks the first patient from the synthea manifest, calls all 6 tools,
and asserts each returns a non-error result (empty list is acceptable for
ImagingStudy / DocumentReference — Synthea doesn't emit those for this module).

Exit codes:
  0 — all tools callable, no exceptions
  1 — one or more tools errored OR HAPI not reachable
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env", override=False)

MANIFEST_PATH = REPO_ROOT / "data/synthea-config/manifest.json"
FHIR_BASE_URL = os.getenv("FHIR_BASE_URL", "http://localhost:8082/fhir")

_failures: list[str] = []


def _ok(msg: str) -> None:
    print(f"  [ OK ] {msg}")


def _fail(msg: str) -> None:
    _failures.append(msg)
    print(f"  [FAIL] {msg}")


def _info(msg: str) -> None:
    print(f"  [info] {msg}")


async def _run_tools(patient_id: str) -> None:
    from prior_auth_copilot.evidence.tools import (
        find_conditions,
        find_documents,
        find_imaging_studies,
        find_medication_history,
        find_observations,
        find_procedures,
    )

    # ── Tool 1: find_observations ──────────────────────────────────────────
    try:
        obs = await find_observations(patient_id)
        _ok(f"find_observations → {len(obs)} result(s)")
    except Exception as exc:
        _fail(f"find_observations raised: {exc}")

    # ── Tool 2: find_conditions ────────────────────────────────────────────
    try:
        conds = await find_conditions(patient_id)
        _ok(f"find_conditions → {len(conds)} result(s)")
        if conds:
            codes = [
                c.get("code", {}).get("coding", [{}])[0].get("code", "?")
                for c in conds[:3]
            ]
            _info(f"  first codes: {codes}")
    except Exception as exc:
        _fail(f"find_conditions raised: {exc}")

    # ── Tool 3: find_procedures ────────────────────────────────────────────
    try:
        procs = await find_procedures(patient_id)
        _ok(f"find_procedures → {len(procs)} result(s)")
    except Exception as exc:
        _fail(f"find_procedures raised: {exc}")

    # ── Tool 4: find_medication_history ────────────────────────────────────
    try:
        meds = await find_medication_history(patient_id)
        _ok(f"find_medication_history → {len(meds)} result(s)")
    except Exception as exc:
        _fail(f"find_medication_history raised: {exc}")

    # ── Tool 5: find_imaging_studies ───────────────────────────────────────
    try:
        imgs = await find_imaging_studies(patient_id)
        # Synthea low_back_pain module does not emit ImagingStudy — empty is expected.
        _ok(f"find_imaging_studies → {len(imgs)} result(s) (0 expected for this module)")
    except Exception as exc:
        _fail(f"find_imaging_studies raised: {exc}")

    # ── Tool 6: find_documents ─────────────────────────────────────────────
    try:
        docs = await find_documents(patient_id)
        # Synthea low_back_pain module does not emit DocumentReference — empty is expected.
        _ok(f"find_documents → {len(docs)} result(s) (0 expected for this module)")
    except Exception as exc:
        _fail(f"find_documents raised: {exc}")


async def main() -> None:
    print(f"smoke_mcp_tools.py — FHIR_BASE_URL: {FHIR_BASE_URL}\n")

    # ── Verify manifest exists ─────────────────────────────────────────────
    if not MANIFEST_PATH.exists():
        print("ERROR: manifest.json not found. Run `make load-synthea` first.")
        sys.exit(1)

    with open(MANIFEST_PATH, encoding="utf-8") as fh:
        manifest = json.load(fh)

    patients = manifest.get("patients", [])
    if not patients:
        print("ERROR: manifest.json has no patients.")
        sys.exit(1)

    # Use first complete patient for the smoke test.
    complete = [p for p in patients if p.get("path") == "complete"]
    test_patient = (complete or patients)[0]
    patient_id = test_patient["patient_id"]
    print(f"Test patient : {patient_id}  (path: {test_patient['path']})\n")

    # ── Run all 6 tools ────────────────────────────────────────────────────
    print("Calling all 6 evidence tools ...")
    try:
        await _run_tools(patient_id)
    except Exception as exc:
        print(f"\nUnhandled error: {exc}")
        print(
            "If this is an httpx connection error, ensure HAPI is running: make fhir-up"
        )
        sys.exit(1)

    # ── Summary ────────────────────────────────────────────────────────────
    print()
    if _failures:
        print(f"SMOKE TOOLS FAILED — {len(_failures)} tool(s) errored:")
        for f in _failures:
            print(f"  • {f}")
        sys.exit(1)
    else:
        print("SMOKE TOOLS PASSED — all 6 tools callable.")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
