# Persona — Payer Reviewer

**Name (composite)**: Linda Okafor, RN · 9 years payer-side UM · works for a regional Blue plan, reviews ~80 PA requests per day across imaging and specialty pharmacy.

## Day in the life (with PA today)

- Receives PAs by fax, portal upload, and (increasingly) X12 278.
- Spends most of her time **parsing unstructured provider justifications** to map them back to her plan's medical policy.
- A "clean" request is one where the provider has cited the right policy section and attached the right documents. Maybe 1 in 5 are clean. The rest require a callback or a request-for-additional-information.
- CMS-0057 is going to make her job both easier (structured inputs) and harder (volume goes up because the friction goes down).

## What she needs from incoming PAs

1. **Standards-compliant PAS Bundles** — that pass `$validate` against `davinci-pas`. No custom extensions she has to decode.
2. **Citations to her plan's policy**, by policy ID and paragraph — not "as per medical literature".
3. **Structured DTR-style data** where her policy requires structured inputs (e.g., BMI for GLP-1, conservative therapy duration for MRI lumbar spine).
4. **An audit trail of how the request was assembled** — for appeals defensibility.

## What would make her route this to "additional information needed"

- A PAS Bundle that fails `$validate`.
- A cited policy paragraph she can't locate in her own policy document.
- A justification narrative that contradicts the structured DTR data.
- Missing prior-conservative-therapy documentation when the policy requires it.

## How this co-pilot serves her

- **Bundle conformance is gated in CI** — the PAS Bundle Builder won't emit a Bundle that fails `$validate` against `us-core` + `davinci-pas`.
- The Reasoner emits citations as `policyId + section + paragraph` triples — directly addressable in her workflow.
- Reviewer-approved drafts include an **audit trace** (LangGraph checkpoint serialized into a `Provenance` resource attached to the Bundle).
- Structured DTR data is captured during the Reasoner step using the payer's published `Questionnaire` resource where available.

She's not our user. But she's the user whose definition of "good" is the one our PAs are graded against. Every eval gate is calibrated to her acceptance criteria.
