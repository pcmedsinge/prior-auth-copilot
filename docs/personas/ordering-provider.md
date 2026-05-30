# Persona — Ordering Provider

**Name (composite)**: Dr. Anjali Rao, MD · 7 years post-residency · internal medicine, multi-specialty group practice, suburban US Midwest.

## Day in the life (with PA today)

- Sees 22–26 patients per day in 15-minute slots.
- Orders an MRI lumbar spine, GLP-1 for obesity, or a specialty referral — and learns 36 hours later that a PA is required.
- Either dictates a justification letter herself, or punts it to the practice's PA coordinator who plays phone tag with the payer.
- **Median time-to-decision**: 5–10 business days. Roughly 1 in 4 are initially denied; ~70% of denied are overturned on peer-to-peer.
- The cognitive tax is the worst part — *not* the time. She doesn't trust that the order will land, so she pre-emptively orders a cheaper second-line workup "just in case".

## What she needs from this tool

1. **Tell me at order-entry if PA is needed and why** — via CDS Hooks / CRD, not a fax three days later.
2. **If PA is needed, draft the justification for me** — pulling from the chart I already wrote in. Don't make me retype the H&P.
3. **Show me the payer's actual criteria**, in plain English, with a citation I can point at on a peer-to-peer call.
4. **Don't surprise me** — if the model is unsure, say so; route to the UM nurse before bothering me again.

## What would make her stop using it

- Anything that adds a click to her existing order-entry workflow without removing two.
- A justification draft she has to substantially rewrite. (If she has to rewrite >30% of it, she loses trust and reverts to dictating from scratch.)
- Any UI that exposes raw FHIR. She should never see the word "Bundle".

## How this co-pilot serves her

- Triggers via **CDS Hooks (order-select)** so the PA hint appears *in* her EHR ordering workflow — see ADR-0001 on why orchestration runs in LangGraph behind the hook.
- The Reasoner produces a 1-paragraph plain-English justification + 2–3 citations.
- The Reviewer (UM nurse) is the human between her and the payer — she never has to babysit the submission.
