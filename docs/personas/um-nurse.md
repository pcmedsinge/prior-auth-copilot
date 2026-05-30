# Persona — Utilization Management (UM) Nurse

**Name (composite)**: Marcus Hill, RN, BSN · 12 years clinical (med-surg, then UM) · works in a provider-side PA cell of 6 nurses + 1 medical director.

## Day in the life (with PA today)

- Carries a queue of 30–60 open PA requests per day.
- For each: pulls the chart, hunts for the supporting labs/imaging/notes, writes the justification, attaches it in the payer portal, waits.
- Spends ~60% of his day on **evidence assembly** (find the right note, the right lab value, the right imaging report), ~25% on **portal data entry**, ~15% on **peer-to-peer coordination**.
- Every payer has a different portal. Every portal has a different field order. None of them autofill from the chart.

## What he needs from this tool

1. **A pre-assembled evidence package** — every relevant lab, note, imaging report, prior conservative therapy attempt — surfaced *with the policy criterion it satisfies*.
2. **An editable draft justification** — he wants to be the editor, not the author. Editing a good draft takes 2 minutes; writing from scratch takes 20.
3. **Traceability** — for every claim in the draft, one click to the source FHIR resource. If he can't trace it, he doesn't trust it.
4. **A "send back to the model" button** when the draft is wrong — feeds the eval harness without making him fill out a form.

## What would make him stop using it

- Drafts that confidently cite evidence that doesn't exist. (One hallucination destroys months of trust.)
- A UI that buries the source link.
- Any tool that auto-submits to the payer without his explicit click. He owns the submission. Always.

## How this co-pilot serves him

- The Evidence Gatherer attaches **every cited FHIR resource by reference** (`Observation/123`) — one click opens the source.
- The Reasoner output is structured as `claim → criterion → citation` triples. Hallucinated citations are caught by a deterministic checker before the draft ever reaches Marcus.
- The Reviewer agent is *his* workspace: pause, edit, accept, send-back-with-feedback. The "send back" action writes a structured feedback record to the eval harness (Phase 4.5).
- **No auto-submit. Ever.** This is enforced architecturally — the `submit_to_payer` tool is gated on a Reviewer-approved checkpoint.
