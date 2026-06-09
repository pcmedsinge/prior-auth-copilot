#!/usr/bin/env python3
"""
load_synthea.py â€” Synthea pipeline for Prior-Auth Co-pilot Phase 4.2

Subcommands
-----------
  generate   Run the Synthea Docker container to produce ~200 FHIR bundles.
  curate     Score bundles against the PA checklist; write manifest.json.
  load       POST curated bundles to the local HAPI FHIR server (idempotent).

Usage
-----
  python scripts/load_synthea.py generate
  python scripts/load_synthea.py curate
  python scripts/load_synthea.py load
  python scripts/load_synthea.py generate curate load   # chain all three

Environment  (.env or environment variables)
-----------
  FHIR_BASE_URL       default: http://localhost:8082/fhir
  SYNTHEA_POOL_SIZE   default: 200
  SYNTHEA_FINAL_SIZE  default: 50
  SYNTHEA_SEEDS_FILE  default: data/synthea-config/seeds.txt
  SYNTHEA_OUTPUT_DIR  default: out/synthea/fhir
  SYNTHEA_LOAD_TAG    default: synthea-v1
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

# Resolve repo root relative to this script so the script can be run from any cwd.
REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env", override=False)

# ---------------------------------------------------------------------------
# Config (all overridable via env / .env)
# ---------------------------------------------------------------------------

FHIR_BASE_URL = os.getenv("FHIR_BASE_URL", "http://localhost:8082/fhir")
POOL_SIZE = int(os.getenv("SYNTHEA_POOL_SIZE", "200"))
FINAL_SIZE = int(os.getenv("SYNTHEA_FINAL_SIZE", "20"))
SEEDS_FILE = REPO_ROOT / os.getenv("SYNTHEA_SEEDS_FILE", "data/synthea-config/seeds.txt")
OUTPUT_DIR = REPO_ROOT / os.getenv("SYNTHEA_OUTPUT_DIR", "out/synthea/fhir/fhir")
LOAD_TAG = os.getenv("SYNTHEA_LOAD_TAG", "synthea-v1")
MANIFEST_PATH = REPO_ROOT / "data/synthea-config/manifest.json"

# Counts of each path that go into the final set.
# Note: Synthea's age distribution (~9% hit the complete path with our Age_Guard â‰¥30).
# With a 200-patient pool expect ~18-20 complete.  Adjust here if pool is larger.
FINAL_COMPLETE_COUNT = 15
FINAL_MISSING_COUNT = 5  # evidence-missing cases (any of the 3 denial paths)

# PA checklist SNOMED / RxNorm / LOINC codes (must match the GMF module).
SNOMED_LOW_BACK_PAIN = "279039007"
SNOMED_RADICULOPATHY = "57054005"
SNOMED_PT_PROCEDURE = "36048009"
RXNORM_IBUPROFEN = "197803"
LOINC_PAIN_SCORE = "72514-3"


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _log(msg: str) -> None:
    print(f"[load_synthea] {msg}", flush=True)


def _read_seeds(path: Path) -> list[int]:
    """Parse seeds.txt â€” integers, skipping blank lines and # comments."""
    seeds: list[int] = []
    with open(path) as fh:
        for line in fh:
            stripped = line.split("#")[0].strip()
            if stripped:
                seeds.append(int(stripped))
    if not seeds:
        raise ValueError(f"No seeds found in {path}")
    return seeds


# ---------------------------------------------------------------------------
# Subcommand: generate
# ---------------------------------------------------------------------------


def cmd_generate() -> None:
    """
    Run the Synthea Docker image once per seed to produce FHIR bundles.
    Bundles are written to OUTPUT_DIR (mounted as /output inside the container).
    """
    _log(f"Generate â€” pool size: {POOL_SIZE}, seeds file: {SEEDS_FILE}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    seeds = _read_seeds(SEEDS_FILE)
    primary_seed = seeds[0]

    # Batch size per seed run.  With one primary seed we generate the full pool.
    # If more seeds are present they are used as fallback (curate will union them).
    batch_size = POOL_SIZE

    _log(f"Using primary seed {primary_seed} â€” generating {batch_size} patients ...")

    # docker compose run --rm synthea <args>
    # We pass the custom modules dir via -d /modules (already mounted in compose).
    # We restrict to only the custom module via -m low_back_pain for speed.
    cmd = [
        "docker", "compose", "run", "--rm",
        "synthea",
        "-p", str(batch_size),
        "-s", str(primary_seed),
        "-d", "/modules",
        "-m", "low_back_pain",
        "--exporter.baseDirectory", "/output/",
    ]

    _log(f"Running: {' '.join(cmd)}")

    result = subprocess.run(cmd, cwd=str(REPO_ROOT))
    if result.returncode != 0:
        _log("ERROR: Synthea container exited with a non-zero code.")
        sys.exit(result.returncode)

    bundle_files = list(OUTPUT_DIR.glob("*.json"))
    _log(f"Generate complete â€” {len(bundle_files)} bundle(s) in {OUTPUT_DIR}")

    if len(bundle_files) < FINAL_SIZE:
        _log(
            f"WARNING: Only {len(bundle_files)} bundles produced; need {FINAL_SIZE}. "
            "Consider adding fallback seeds to seeds.txt or increasing SYNTHEA_POOL_SIZE."
        )


# ---------------------------------------------------------------------------
# Subcommand: curate
# ---------------------------------------------------------------------------


def _extract_patient_id(bundle: dict) -> str | None:
    """Return the first Patient resource id from a FHIR Bundle."""
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        if resource.get("resourceType") == "Patient":
            return resource.get("id")
    return None


def _resource_type_entries(bundle: dict, resource_type: str) -> list[dict]:
    return [
        e["resource"]
        for e in bundle.get("entry", [])
        if e.get("resource", {}).get("resourceType") == resource_type
    ]


def _has_code(coding_list: list[dict], system_fragment: str, code: str) -> bool:
    """Check if any coding in a list matches system (substring) + code."""
    for coding in coding_list:
        sys = coding.get("system", "")
        if system_fragment.lower() in sys.lower() and coding.get("code") == code:
            return True
    return False


def _codings_from_resource(resource: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Collect all codings from a FHIR resource.
    Handles multiple resource types:
      - Most resources: code.coding[]
      - MedicationRequest: medicationCodeableConcept.coding[]
      - FHIR R5 medication.concept.coding[] (future-proofing)
    """
    codings: list[dict] = []
    # Standard path
    codings.extend(resource.get("code", {}).get("coding", []))
    # MedicationRequest R4 path
    codings.extend(resource.get("medicationCodeableConcept", {}).get("coding", []))
    # MedicationRequest R5 path (future-proofing)
    codings.extend(resource.get("medication", {}).get("concept", {}).get("coding", []))
    return codings


def _score_bundle(bundle: dict) -> dict:
    """
    Score a single FHIR transaction Bundle against the MRI lumbar spine PA checklist.

    Returns a dict with:
        patient_id          str
        path                str  â€” complete | missing_conservative | short_conservative | nsaids_only | unknown
        evidence_flags      dict â€” individual boolean checklist items
        missing_reasons     list[str] â€” human-readable reasons (non-empty for denial paths)
    """
    patient_id = _extract_patient_id(bundle) or "unknown"

    conditions = _resource_type_entries(bundle, "Condition")
    med_requests = _resource_type_entries(bundle, "MedicationRequest")
    procedures = _resource_type_entries(bundle, "Procedure")
    observations = _resource_type_entries(bundle, "Observation")

    # --- Checklist items ---
    has_lbp = any(
        _has_code(_codings_from_resource(c), "snomed", SNOMED_LOW_BACK_PAIN)
        for c in conditions
    )
    has_radiculopathy = any(
        _has_code(_codings_from_resource(c), "snomed", SNOMED_RADICULOPATHY)
        for c in conditions
    )
    has_nsaid = any(
        _has_code(_codings_from_resource(m), "rxnorm", RXNORM_IBUPROFEN)
        for m in med_requests
    )
    has_pain_score = any(
        _has_code(_codings_from_resource(o), "loinc", LOINC_PAIN_SCORE)
        for o in observations
    )

    # PT sessions: collect all Procedure dates for SNOMED 36048009.
    pt_dates: list[str] = []
    for proc in procedures:
        if _has_code(_codings_from_resource(proc), "snomed", SNOMED_PT_PROCEDURE):
            performed = proc.get("performedPeriod", {}).get("start") or proc.get(
                "performedDateTime", ""
            )
            if performed:
                pt_dates.append(performed)

    has_pt = len(pt_dates) >= 1

    # Two sessions >= 28 days apart?
    has_two_pt_sessions_threshold = False
    if len(pt_dates) >= 2:
        from datetime import datetime

        parsed = sorted(
            datetime.fromisoformat(d[:10]) for d in pt_dates
        )
        delta_days = (parsed[-1] - parsed[0]).days
        has_two_pt_sessions_threshold = delta_days >= 28

    # --- Classification ---
    missing_reasons: list[str] = []

    if has_lbp and has_nsaid and has_pt and has_two_pt_sessions_threshold and has_pain_score:
        path = "complete"
    elif has_lbp and not has_nsaid and not has_pt:
        path = "missing_conservative"
        missing_reasons.append("No NSAID prescription documented")
        missing_reasons.append("No physical therapy procedure documented")
    elif has_lbp and has_nsaid and has_pt and not has_two_pt_sessions_threshold:
        path = "short_conservative"
        missing_reasons.append(
            f"Only {len(pt_dates)} PT session(s) â€” gap between sessions < 28 days"
        )
    elif has_lbp and has_nsaid and not has_pt:
        path = "nsaids_only"
        missing_reasons.append("No physical therapy procedure documented")
    else:
        path = "unknown"
        missing_reasons.append("Bundle did not match any expected evidence path")

    return {
        "patient_id": patient_id,
        "path": path,
        "evidence_flags": {
            "has_lbp": has_lbp,
            "has_radiculopathy": has_radiculopathy,
            "has_nsaid": has_nsaid,
            "has_pain_score": has_pain_score,
            "has_pt": has_pt,
            "has_two_pt_sessions_threshold": has_two_pt_sessions_threshold,
        },
        "missing_reasons": missing_reasons,
    }


def cmd_curate() -> None:
    """
    Score all bundles in OUTPUT_DIR, select FINAL_COMPLETE_COUNT complete +
    FINAL_MISSING_COUNT evidence-missing patients, write manifest.json.
    """
    _log(f"Curate â€” scanning {OUTPUT_DIR} ...")

    bundle_files = sorted(OUTPUT_DIR.glob("*.json"))
    if not bundle_files:
        _log(f"ERROR: No bundle files found in {OUTPUT_DIR}. Run 'generate' first.")
        sys.exit(1)

    _log(f"Found {len(bundle_files)} bundle(s) â€” scoring ...")

    complete: list[dict] = []
    missing: list[dict] = []
    unknown_count = 0

    for bundle_path in bundle_files:
        with open(bundle_path, encoding="utf-8") as fh:
            try:
                bundle = json.load(fh)
            except json.JSONDecodeError as exc:
                _log(f"WARNING: Could not parse {bundle_path.name}: {exc}")
                continue

        score = _score_bundle(bundle)
        record = {
            "patient_id": score["patient_id"],
            "bundle_path": str(bundle_path.relative_to(REPO_ROOT)),
            "path": score["path"],
            "evidence_flags": score["evidence_flags"],
            "missing_reasons": score["missing_reasons"],
        }

        if score["path"] == "complete":
            complete.append(record)
        elif score["path"] in ("missing_conservative", "short_conservative", "nsaids_only"):
            missing.append(record)
        else:
            unknown_count += 1

    _log(
        f"Scored: {len(complete)} complete, {len(missing)} evidence-missing, "
        f"{unknown_count} unknown/unmatched"
    )

    # Guard: need enough of each type.
    if len(complete) < FINAL_COMPLETE_COUNT:
        _log(
            f"ERROR: Only {len(complete)} complete patients â€” need {FINAL_COMPLETE_COUNT}. "
            "Re-run generate with a larger pool or additional seeds."
        )
        sys.exit(1)

    if len(missing) < FINAL_MISSING_COUNT:
        _log(
            f"ERROR: Only {len(missing)} evidence-missing patients â€” need {FINAL_MISSING_COUNT}. "
            "Re-run generate with a larger pool or additional seeds."
        )
        sys.exit(1)

    selected_complete = complete[:FINAL_COMPLETE_COUNT]
    selected_missing = missing[:FINAL_MISSING_COUNT]
    selected = selected_complete + selected_missing

    manifest = {
        "version": "1",
        "generated_by": "load_synthea.py curate",
        "total": len(selected),
        "complete_count": len(selected_complete),
        "evidence_missing_count": len(selected_missing),
        "patients": selected,
    }

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    _log(f"Manifest written â†’ {MANIFEST_PATH}")
    _log(f"  {len(selected_complete)} complete patients")
    _log(f"  {len(selected_missing)} evidence-missing patients:")
    for p in selected_missing:
        _log(f"    [{p['path']}] {p['patient_id']} â€” {'; '.join(p['missing_reasons'])}")


# ---------------------------------------------------------------------------
# Subcommand: load
# ---------------------------------------------------------------------------

import copy  # noqa: E402  (imported here to keep top-of-file imports minimal)

import requests  # noqa: E402


# Tag injected into every resource meta before upload.
_TAG_SYSTEM = "https://github.com/pcmedsinge/prior-auth-copilot"
_TAG_ENTRY = {"system": _TAG_SYSTEM, "code": LOAD_TAG}

_FHIR_HEADERS = {
    "Content-Type": "application/fhir+json",
    "Accept": "application/fhir+json",
}

# Resource types we purge before a fresh load (ordered to respect referential integrity).
_PURGEABLE_TYPES = [
    "MedicationRequest",
    "Procedure",
    "Observation",
    "Condition",
    "Encounter",
    "Patient",
    "Practitioner",
    "Organization",
    "Location",
]


def _inject_tag(bundle: dict) -> dict:
    """
    Return a deep copy of the bundle with _TAG_ENTRY added to every resource's
    meta.tag list.  Does not mutate the input.
    """
    tagged = copy.deepcopy(bundle)
    for entry in tagged.get("entry", []):
        resource = entry.get("resource")
        if not isinstance(resource, dict):
            continue
        meta = resource.setdefault("meta", {})
        tags: list[dict] = meta.setdefault("tag", [])
        # Avoid duplicates if called twice.
        if not any(t.get("code") == LOAD_TAG for t in tags):
            tags.append(_TAG_ENTRY)
    return tagged


def _purge_tagged_resources(session: requests.Session) -> None:
    """
    Delete every resource in HAPI that carries the LOAD_TAG.
    Iterates resource types in an order that avoids referential-integrity errors.
    Uses HAPI's _tag search parameter + _expunge=true for hard deletes.
    """
    tag_param = f"{_TAG_SYSTEM}|{LOAD_TAG}"
    purged_total = 0

    for rtype in _PURGEABLE_TYPES:
        url = f"{FHIR_BASE_URL}/{rtype}"
        params = {"_tag": tag_param, "_summary": "count"}
        resp = session.get(url, params=params, headers=_FHIR_HEADERS, timeout=30)
        if resp.status_code != 200:
            _log(f"  WARNING: could not count {rtype} â€” {resp.status_code}")
            continue

        total = resp.json().get("total", 0)
        if total == 0:
            continue

        # HAPI conditional delete: DELETE /fhir/ResourceType?_tag=system|code
        del_url = f"{FHIR_BASE_URL}/{rtype}"
        del_resp = session.delete(
            del_url, params={"_tag": tag_param}, headers=_FHIR_HEADERS, timeout=60
        )
        if del_resp.status_code not in (200, 204):
            _log(f"  WARNING: delete {rtype} returned {del_resp.status_code}")
        else:
            purged_total += total
            _log(f"  Purged {total} {rtype} resource(s)")

    _log(f"Purge complete â€” {purged_total} resource(s) removed")


def _post_bundle(session: requests.Session, bundle: dict, label: str) -> bool:
    """
    Load a Synthea FHIR bundle into HAPI using PUT with Synthea resource IDs.

    Synthea uses urn:uuid: as fullUrl and as cross-resource references.
    We build a map from urn:uuid:X -> ResourceType/X using the bundle's own
    fullUrl entries, then rewrite all .reference fields before PUTting each
    resource. HAPI accepts PUT /{Type}/{id} and stores the resource with
    the Synthea UUID as its logical ID.

    Load order ensures referenced resources exist before referencing ones.
    """
    _ORDER = [
        "Practitioner", "Organization", "Location",
        "Patient",
        "Encounter",  # must come before Condition/Procedure/Observation which reference it
        "Condition", "Procedure", "MedicationRequest",
        "Observation", "ImagingStudy",
    ]

    # Build urn -> ResourceType/id map from bundle fullUrls
    urn_to_ref: dict[str, str] = {}
    for entry in bundle.get("entry", []):
        full_url = entry.get("fullUrl", "")
        resource = entry.get("resource", {})
        rtype = resource.get("resourceType", "")
        rid = resource.get("id", "")
        if full_url.startswith("urn:uuid:") and rtype and rid:
            urn_to_ref[full_url] = f"{rtype}/{rid}"

    # Also build a map of conditional refs like "Practitioner?identifier=..."
    # -> first matching Practitioner id in this bundle
    pract_by_npi: dict[str, str] = {}
    org_by_npi: dict[str, str] = {}
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        rtype = resource.get("resourceType", "")
        rid = resource.get("id", "")
        if not rid:
            continue
        for ident in resource.get("identifier", []):
            val = ident.get("value", "")
            if rtype == "Practitioner" and val:
                pract_by_npi[val] = f"Practitioner/{rid}"
            elif rtype == "Organization" and val:
                org_by_npi[val] = f"Organization/{rid}"

    def _resolve_conditional(ref: str) -> str:
        """Resolve Synthea conditional references like 'Practitioner?identifier=sys|val'."""
        if "?identifier=" in ref:
            val = ref.split("|")[-1]  # get the NPI value after the |
            rtype_prefix = ref.split("?")[0]
            if rtype_prefix == "Practitioner" and val in pract_by_npi:
                return pract_by_npi[val]
            if rtype_prefix == "Organization" and val in org_by_npi:
                return org_by_npi[val]
            return ""  # drop unresolvable conditional refs
        return ref

    def _rewrite(obj: Any) -> Any:
        """Replace all urn:uuid: and conditional references with ResourceType/id."""
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if k == "reference" and isinstance(v, str):
                    if v.startswith("urn:uuid:"):
                        out[k] = urn_to_ref.get(v, v)
                    elif "?" in v:
                        resolved = _resolve_conditional(v)
                        if resolved:  # only include if resolvable
                            out[k] = resolved
                        # else: skip this reference entirely
                    else:
                        out[k] = v
                else:
                    out[k] = _rewrite(v)
            return out
        if isinstance(obj, list):
            return [_rewrite(i) for i in obj]
        return obj

    resources_by_type: dict[str, list] = {}
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        rtype = resource.get("resourceType", "")
        rid = resource.get("id", "")
        if rtype in _ORDER and rid:
            resources_by_type.setdefault(rtype, []).append(resource)

    for rtype in _ORDER:
        for resource in resources_by_type.get(rtype, []):
            rid = resource["id"]
            rewritten = _rewrite(copy.deepcopy(resource))
            resp = session.put(
                f"{FHIR_BASE_URL}/{rtype}/{rid}",
                json=rewritten,
                headers=_FHIR_HEADERS,
                timeout=30,
            )
            if resp.status_code not in (200, 201):
                _log(f"  WARN: {rtype}/{rid} PUT failed {resp.status_code} - skipping")

    return True


def cmd_load() -> None:
    """
    Read manifest.json, inject the load tag into every bundle, purge any
    previously-loaded tagged resources from HAPI, then POST each bundle.
    Safe to re-run (idempotent via tag purge).
    """
    _log(f"Load â€” reading manifest: {MANIFEST_PATH}")

    if not MANIFEST_PATH.exists():
        _log("ERROR: manifest.json not found. Run 'curate' first.")
        sys.exit(1)

    with open(MANIFEST_PATH, encoding="utf-8") as fh:
        manifest = json.load(fh)

    patients = manifest.get("patients", [])
    _log(f"Manifest: {len(patients)} patient(s) to load â†’ {FHIR_BASE_URL}")

    session = requests.Session()

    # Verify HAPI is reachable before doing anything destructive.
    try:
        ping = session.get(f"{FHIR_BASE_URL}/metadata", timeout=10)
        ping.raise_for_status()
    except requests.RequestException as exc:
        _log(f"ERROR: HAPI not reachable at {FHIR_BASE_URL} â€” {exc}")
        _log("Run `make fhir-up` and wait for the server to be ready.")
        sys.exit(1)

    # Purge previous load (idempotency).
    _log("Purging previously-loaded tagged resources ...")
    _purge_tagged_resources(session)

    # Load each curated patient bundle.
    loaded = 0
    failed = 0
    for record in patients:
        bundle_path = REPO_ROOT / record["bundle_path"]
        patient_id = record["patient_id"]

        if not bundle_path.exists():
            _log(f"  WARNING: bundle file missing for {patient_id}: {bundle_path}")
            failed += 1
            continue

        with open(bundle_path, encoding="utf-8") as fh:
            try:
                bundle = json.load(fh)
            except json.JSONDecodeError as exc:
                _log(f"  WARNING: could not parse bundle for {patient_id}: {exc}")
                failed += 1
                continue

        tagged_bundle = _inject_tag(bundle)
        success = _post_bundle(session, tagged_bundle, patient_id)
        if success:
            loaded += 1
        else:
            failed += 1

    _log(f"Load complete â€” {loaded} loaded, {failed} failed")
    if failed > 0:
        _log("Some bundles failed to load. Check the errors above.")
        sys.exit(1)

    _log(f"Verify: curl '{FHIR_BASE_URL}/Patient?_summary=count'")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="load_synthea.py",
        description="Synthea â†’ HAPI FHIR pipeline for Prior-Auth Co-pilot",
    )
    parser.add_argument(
        "subcommands",
        nargs="+",
        choices=["generate", "curate", "load"],
        help="One or more subcommands to run in order.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    for sub in args.subcommands:
        if sub == "generate":
            cmd_generate()
        elif sub == "curate":
            cmd_curate()
        elif sub == "load":
            cmd_load()


if __name__ == "__main__":
    main()


