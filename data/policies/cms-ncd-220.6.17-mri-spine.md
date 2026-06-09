# CMS National Coverage Determination — MRI of the Spine
# NCD 220.6.17 | Source: CMS.gov | Effective: Ongoing
# https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?NCDId=286
#
# This file is the authoritative policy text used by the Medical Necessity
# Reasoner.  Each section delimited by "## Section" becomes one retrievable
# chunk in the LanceDB policy store.
#
# policy_id: cms-ncd-220.6.17
# service:   MRI of the Spine (Lumbar, Cervical, Thoracic)
# payer:     CMS Medicare (applies to all Medicare-participating providers)

## Section A — Indications: Covered Conditions

Medicare covers MRI of the spine when the clinical record documents one or more
of the following indications:

1. **Failed conservative therapy**: The patient has received an adequate course
   of conservative treatment — defined as at least six (6) weeks of one or more
   of the following: physical therapy, chiropractic care, structured home
   exercise program, or analgesic/anti-inflammatory pharmacotherapy — and
   symptoms have not resolved or have worsened.

2. **Neurological deficit**: The patient presents with objective neurological
   findings, including but not limited to radiculopathy, myelopathy, motor
   weakness, sensory deficit, or abnormal deep-tendon reflexes consistent with
   nerve-root or cord compression.

3. **Red-flag symptoms**: The patient presents with one or more clinical
   red-flag symptoms that necessitate urgent imaging, including:
   - New-onset bowel or bladder dysfunction
   - Progressive neurological deficit
   - Saddle anaesthesia
   - Fever with back pain (concern for epidural abscess or discitis)
   - History of malignancy with new back pain
   - Unexplained significant weight loss with back pain
   - Trauma with suspected spinal fracture

4. **Prior surgical evaluation**: The patient is being evaluated for spinal
   surgery and pre-operative imaging is required to plan the procedure.

5. **Post-surgical follow-up**: The patient has undergone prior spinal surgery
   and post-operative MRI is indicated to evaluate for complications, recurrent
   disc herniation, or hardware failure.

6. **Known or suspected neoplasm or infection**: The patient has known or
   suspected spinal neoplasm, abscess, osteomyelitis, or discitis.

## Section B — Non-Covered Conditions (Exclusions)

Medicare does NOT cover MRI of the spine for the following:

1. **Non-specific low back pain without conservative therapy**: Routine or
   first-line imaging for uncomplicated acute low back pain in the absence of
   red-flag symptoms and without an adequate trial of conservative therapy.
   Clinical evidence does not support early MRI for non-specific back pain; it
   does not improve outcomes and may lead to unnecessary intervention.

2. **Screening in asymptomatic patients**: MRI performed solely as a screening
   study in patients without symptoms attributable to a spinal disorder.

3. **Repeat imaging without clinical change**: Repeat MRI within 12 months of a
   prior spinal MRI when there has been no significant change in the patient's
   clinical condition, no new neurological findings, and no new red-flag
   symptoms.

4. **Contraindicated patients**: MRI is contraindicated in patients with
   non-MRI-compatible implanted devices (e.g., pacemakers, certain cochlear
   implants) unless clearance has been obtained from the implant manufacturer
   and the ordering provider.

## Section C — Documentation Requirements

The medical record submitted in support of a Prior Authorization request for
spinal MRI must include:

1. **Diagnosis and symptom onset**: The primary diagnosis (ICD-10-CM code),
   date of symptom onset, and a clinical description of the presenting complaint.

2. **Conservative therapy documentation**: For non-emergent requests, the
   medical record must document the type, duration, and frequency of
   conservative treatment administered, including provider name, dates of
   service, and the patient's response (improved, unchanged, worsened).

3. **Physical examination findings**: Documented neurological examination
   findings, including assessment of motor strength, sensory function,
   deep-tendon reflexes, and straight-leg raise (or equivalent) where
   applicable.

4. **Prior imaging results**: If prior imaging (X-ray, CT) has been performed,
   the results must be included. MRI should be ordered only if prior imaging
   does not provide sufficient diagnostic information.

5. **Clinical indication**: The ordering provider must document the specific
   clinical indication from Section A that justifies the MRI request.

## Section D — Conservative Therapy: Minimum Duration and Definition

For the purposes of this NCD, "adequate conservative therapy" is defined as:

- **Duration**: A minimum of six (6) consecutive weeks of treatment.
- **Acceptable modalities** (one or more required):
  - Structured physical therapy (PT) — minimum 2 sessions per month with a
    licensed physical therapist
  - Chiropractic manipulation — minimum 4 sessions over the 6-week period
  - Anti-inflammatory or analgesic pharmacotherapy — documented prescription
    of NSAIDs (e.g., ibuprofen, naproxen) or acetaminophen for ≥6 weeks
  - Structured home exercise program — prescribed in writing by a licensed
    provider with documented patient adherence at follow-up
- **Exceptions**: The six-week minimum does not apply when red-flag symptoms
  (Section A, item 3) are present. In those cases, urgent imaging is
  appropriate regardless of prior conservative therapy.

## Section E — Prior Authorization Process

Effective January 1, 2027, payers subject to the CMS Interoperability and
Prior Authorization Final Rule (CMS-0057-F) must implement a FHIR-based
Prior Authorization API conformant with the HL7 Da Vinci Prior Authorization
Support (PAS) Implementation Guide.

PA requests for spinal MRI must be submitted as a FHIR `Claim` resource
conformant with the Da Vinci PAS profile, including:

- `Claim.item[].productOrService` coded with the appropriate CPT procedure code
  (e.g., 72148 — MRI lumbar spine without contrast)
- `Claim.supportingInfo` referencing the relevant clinical documentation
  (Condition, Procedure, MedicationRequest, Observation resources)
- `Claim.patient` referencing the enrollee's FHIR `Patient` resource

Payers must respond within 72 hours for standard PA requests and within
24 hours for urgent requests.
