# MCP Evidence-Retrieval Tools — Prior-Auth Co-pilot

Six tools used by the LangGraph Evidence Gatherer node to assemble the clinical evidence package for an MRI lumbar spine Prior Authorization request.

**Source**: [`src/prior_auth_copilot/evidence/tools.py`](../src/prior_auth_copilot/evidence/tools.py)  
**FHIR server**: `http://localhost:8082/fhir` (see `.env.example`)  
**Backed by**: [`mcp-fhir`](https://github.com/pcmedsinge/fhir-mcp-suite/tree/main/packages/mcp-fhir) → `fhir_search`

---

## Tool 1 — `find_observations`

Retrieve Observation resources (lab results, vital signs, pain scores) for a patient.

**Signature**
```python
async def find_observations(
    patient_id: str,
    code: str | None = None,        # LOINC or SNOMED code
    date_from: str | None = None,   # ISO-8601, e.g. "2023-01-01"
    date_to: str | None = None,
) -> list[dict]
```

**Example — fetch pain score observations**
```python
obs = await find_observations(
    patient_id="abc-123",
    code="72514-3",   # Pain severity 0-10 verbal numeric rating
)
```

**Example response** (one item from the list)
```json
{
  "resourceType": "Observation",
  "id": "obs-001",
  "status": "final",
  "code": {
    "coding": [{"system": "http://loinc.org", "code": "72514-3",
                "display": "Pain severity - 0-10 verbal numeric rating [Score] - Reported"}]
  },
  "valueQuantity": {"value": 7, "unit": "{score}"},
  "effectiveDateTime": "2023-03-15T10:00:00Z"
}
```

---

## Tool 2 — `find_conditions`

Retrieve Condition resources (diagnoses) for a patient.

**Signature**
```python
async def find_conditions(
    patient_id: str,
    category: str | None = None,   # e.g. "problem-list-item"
    code: str | None = None,       # SNOMED or ICD-10 code
) -> list[dict]
```

**Example — fetch all active diagnoses**
```python
conds = await find_conditions(patient_id="abc-123")
```

**Example — fetch low back pain condition specifically**
```python
conds = await find_conditions(patient_id="abc-123", code="279039007")
```

**PA checklist use**: confirms LBP diagnosis (SNOMED `279039007`) and radiculopathy (SNOMED `57054005`) are on record.

---

## Tool 3 — `find_procedures`

Retrieve Procedure resources (physical therapy sessions, surgeries, etc.) for a patient.

**Signature**
```python
async def find_procedures(
    patient_id: str,
    code: str | None = None,        # SNOMED or CPT code
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]
```

**Example — fetch all PT procedure sessions**
```python
procs = await find_procedures(
    patient_id="abc-123",
    code="36048009",   # Physical therapy procedure (SNOMED)
)
```

**PA checklist use**: verifies ≥2 PT sessions with ≥28-day gap between them (the "6-week conservative therapy" threshold).

---

## Tool 4 — `find_medication_history`

Retrieve MedicationRequest resources for a patient.

**Signature**
```python
async def find_medication_history(
    patient_id: str,
    code: str | None = None,     # RxNorm code
    status: str | None = None,   # "active" | "completed" | "stopped"
) -> list[dict]
```

**Example — fetch NSAID prescriptions**
```python
meds = await find_medication_history(
    patient_id="abc-123",
    code="197803",   # Ibuprofen 400 MG Oral Tablet (RxNorm)
)
```

**PA checklist use**: confirms NSAID was prescribed (required conservative therapy step before MRI approval).

---

## Tool 5 — `find_imaging_studies`

Retrieve ImagingStudy resources for a patient.

**Signature**
```python
async def find_imaging_studies(
    patient_id: str,
    modality: str | None = None,    # DICOM modality: "MR", "CT", "XR"
    body_site: str | None = None,   # SNOMED body-site code
) -> list[dict]
```

**Example — check for prior lumbar MRI**
```python
imgs = await find_imaging_studies(patient_id="abc-123", modality="MR")
```

**PA checklist use**: confirms no recent lumbar MRI already on record (avoids duplicate imaging approvals).

> **Note**: The Synthea `low_back_pain` module does not emit ImagingStudy resources — an empty list is expected in Phase 4.2. This tool is exercised in Phase 4.4 when real PA scenarios require checking prior-imaging history.

---

## Tool 6 — `find_documents`

Retrieve DocumentReference resources (clinical notes, referral letters, discharge summaries) for a patient.

**Signature**
```python
async def find_documents(
    patient_id: str,
    doc_type: str | None = None,    # LOINC document type code
    date_from: str | None = None,
) -> list[dict]
```

**Example — fetch consultation notes**
```python
docs = await find_documents(
    patient_id="abc-123",
    doc_type="11488-4",   # Consult note (LOINC)
)
```

**PA checklist use**: retrieves any attached clinical documentation (referring-physician notes, specialist letters) that support the PA request.

> **Note**: The Synthea `low_back_pain` module does not emit DocumentReference resources — an empty list is expected in Phase 4.2.

---

## Running the smoke test

```bash
# Requires: make fhir-up + make load-synthea already completed
make smoke-tools
```

Expected output:
```
  [ OK ] find_observations → N result(s)
  [ OK ] find_conditions → N result(s)
  [ OK ] find_procedures → N result(s)
  [ OK ] find_medication_history → N result(s)
  [ OK ] find_imaging_studies → 0 result(s) (0 expected for this module)
  [ OK ] find_documents → 0 result(s) (0 expected for this module)

SMOKE TOOLS PASSED — all 6 tools callable.
```
