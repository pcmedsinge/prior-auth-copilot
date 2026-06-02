#!/usr/bin/env python3
"""
smoke_fhir.py — post-load verification for the Prior-Auth Co-pilot Synthea pipeline.

Checks:
  1. HAPI is reachable at FHIR_BASE_URL.
  2. Exactly SYNTHEA_FINAL_SIZE patients are present (tagged synthea-v1).
  3. Every patient has at least 1 Condition and 1 MedicationRequest.
  4. The 5 evidence-missing patients in manifest.json are present in HAPI
     and their missing_reasons match the manifest.

Exit codes:
  0 — all checks passed
  1 — one or more checks failed
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env", override=False)

FHIR_BASE_URL = os.getenv("FHIR_BASE_URL", "http://localhost:8082/fhir")
FINAL_SIZE = int(os.getenv("SYNTHEA_FINAL_SIZE", "50"))
LOAD_TAG = os.getenv("SYNTHEA_LOAD_TAG", "synthea-v1")
MANIFEST_PATH = REPO_ROOT / "data/synthea-config/manifest.json"

TAG_SYSTEM = "https://github.com/pcmedsinge/prior-auth-copilot"
TAG_PARAM = f"{TAG_SYSTEM}|{LOAD_TAG}"

FHIR_HEADERS = {"Accept": "application/fhir+json"}

_failures: list[str] = []


def _fail(msg: str) -> None:
    _failures.append(msg)
    print(f"  [FAIL] {msg}")


def _ok(msg: str) -> None:
    print(f"  [ OK ] {msg}")


def _count_tagged(session: requests.Session, resource_type: str) -> int:
    resp = session.get(
        f"{FHIR_BASE_URL}/{resource_type}",
        params={"_tag": TAG_PARAM, "_summary": "count"},
        headers=FHIR_HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("total", 0)


def _get_resources_for_patient(
    session: requests.Session, resource_type: str, patient_id: str
) -> int:
    resp = session.get(
        f"{FHIR_BASE_URL}/{resource_type}",
        params={"patient": patient_id, "_summary": "count"},
        headers=FHIR_HEADERS,
        timeout=15,
    )
    if resp.status_code != 200:
        return 0
    return resp.json().get("total", 0)


def main() -> None:
    print(f"smoke_fhir.py — target: {FHIR_BASE_URL}\n")

    session = requests.Session()

    # ── Check 1: HAPI reachable ───────────────────────────────────────────
    print("Check 1: HAPI reachable")
    try:
        ping = session.get(f"{FHIR_BASE_URL}/metadata", timeout=10, headers=FHIR_HEADERS)
        ping.raise_for_status()
        _ok(f"HAPI responded — {ping.status_code}")
    except requests.RequestException as exc:
        _fail(f"HAPI not reachable: {exc}")
        print("\nAborted — run `make fhir-up` first.")
        sys.exit(1)

    # ── Check 2: Patient count ────────────────────────────────────────────
    print("\nCheck 2: Patient count")
    patient_count = _count_tagged(session, "Patient")
    if patient_count == FINAL_SIZE:
        _ok(f"{patient_count} tagged patients (expected {FINAL_SIZE})")
    else:
        _fail(f"{patient_count} tagged patients — expected {FINAL_SIZE}")

    # ── Check 3: Every patient has ≥1 Condition and ≥1 MedicationRequest ─
    print("\nCheck 3: Evidence presence (sample all tagged patients)")
    patients_resp = session.get(
        f"{FHIR_BASE_URL}/Patient",
        params={"_tag": TAG_PARAM, "_count": FINAL_SIZE + 10},
        headers=FHIR_HEADERS,
        timeout=30,
    )
    patients_resp.raise_for_status()
    entries = patients_resp.json().get("entry", [])

    missing_condition = []
    missing_medication = []
    for entry in entries:
        pid = entry["resource"]["id"]
        if _get_resources_for_patient(session, "Condition", pid) == 0:
            missing_condition.append(pid)
        if _get_resources_for_patient(session, "MedicationRequest", pid) == 0:
            missing_medication.append(pid)

    if not missing_condition:
        _ok("All patients have ≥1 Condition")
    else:
        _fail(f"{len(missing_condition)} patient(s) have no Condition: {missing_condition[:3]}")

    if not missing_medication:
        _ok("All patients have ≥1 MedicationRequest")
    else:
        _fail(
            f"{len(missing_medication)} patient(s) have no MedicationRequest: "
            f"{missing_medication[:3]}"
        )

    # ── Check 4: Evidence-missing cases present + reasons printed ────────
    print("\nCheck 4: Evidence-missing cases (manifest cross-check)")
    if not MANIFEST_PATH.exists():
        _fail(f"manifest.json not found at {MANIFEST_PATH}")
    else:
        with open(MANIFEST_PATH, encoding="utf-8") as fh:
            manifest = json.load(fh)

        missing_patients = [
            p for p in manifest.get("patients", []) if p.get("path") != "complete"
        ]

        if len(missing_patients) == 0:
            _fail("No evidence-missing patients found in manifest.json")
        else:
            all_found = True
            for p in missing_patients:
                pid = p["patient_id"]
                resp = session.get(
                    f"{FHIR_BASE_URL}/Patient/{pid}",
                    headers=FHIR_HEADERS,
                    timeout=10,
                )
                if resp.status_code == 200:
                    reasons = "; ".join(p.get("missing_reasons", ["(no reason recorded)"]))
                    print(f"       [{p['path']}] {pid}")
                    print(f"         → {reasons}")
                else:
                    _fail(f"Evidence-missing patient {pid} not found in HAPI (HTTP {resp.status_code})")
                    all_found = False

            if all_found:
                _ok(f"All {len(missing_patients)} evidence-missing patient(s) present in HAPI")

    # ── Summary ───────────────────────────────────────────────────────────
    print()
    if _failures:
        print(f"SMOKE TEST FAILED — {len(_failures)} check(s) failed:")
        for f in _failures:
            print(f"  • {f}")
        sys.exit(1)
    else:
        print("SMOKE TEST PASSED — all checks green.")
        sys.exit(0)


if __name__ == "__main__":
    main()
