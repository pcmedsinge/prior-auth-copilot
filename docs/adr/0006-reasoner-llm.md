# ADR-0006 — LLM choice for the Medical Necessity Reasoner

- **Status**: Accepted
- **Date**: 2026-06-09
- **Deciders**: Parag Medsinge (tech lead)
- **Supersedes**: —
- **Superseded by**: —

---

## Context

The Medical Necessity Reasoner node (Phase 4.3) must:

1. Read the retrieved EvidencePackage from Phase 4.2 (structured FHIR-backed data).
2. Read the top-k retrieved policy paragraphs from the CMS NCD / payer LCD corpus.
3. For each policy criterion, decide `met` / `not_met` / `unclear` — with the specific evidence resource and the specific policy paragraph cited.
4. Output a structured `Decision` object that the citation checker then verifies against the corpus.
5. Stay within the eval-gate cost ceiling of **< $0.10 per Reasoner run**.

Phase 4.2 used `gpt-4o-mini` for one-line evidence summaries — a simple summarisation task where model quality barely matters. Phase 4.3 is categorically different: the Reasoner must apply multi-step clinical logic over 10–20 dense paragraphs of CMS regulatory text and return a structured JSON decision with precise citations.

The model must handle:
- Long-context reading (full policy section + evidence package in one prompt, potentially 8–12k tokens)
- Structured output (function-calling / `response_format=json_object`)
- Reasoning faithfulness — "I cannot determine this" is correct for borderline cases; fabricating a `met` verdict is a patient-safety failure

Three credible options were evaluated.

## Decision

**Use `gpt-4o` as the Reasoner LLM.**

Model is configurable via `REASONER_MODEL` env var (default: `gpt-4o`). This allows per-contributor override and enables the Phase 4.3 eval harness to run comparative evals across model families without code changes.

## Options considered

### Option A — `gpt-4o` (chosen)

- **Pros**:
  - **Best multi-step reasoning** in the GPT-4 family at the time of decision. Consistent structured-output compliance via `response_format` + function calling.
  - **Long-context performance** — 128k token context window; the full NCD section + evidence package fits comfortably without truncation.
  - **Cost**: at ~4k input + ~800 output tokens per Reasoner call: ~$0.05–0.07 per run. Well within the $0.10 eval gate.
  - **Faithfulness**: GPT-4o is more reliably "uncertain" on borderline cases than `gpt-4o-mini` — critical for the hallucination-rate gate (< 0.05 on no-evidence cases).
  - **JSON output reliability**: structured output via `response_format={"type": "json_object"}` is stable on `gpt-4o`.
- **Cons**:
  - ~5–10× more expensive per call than `gpt-4o-mini`. At eval scale (30 cases × $0.07) = ~$2.10 per full eval run — acceptable.
  - Slower (2–6s per call) vs `gpt-4o-mini` (~0.5–1s). Still within the P50 < 20s latency gate.

### Option B — `gpt-4.1`

OpenAI's latest GPT-4-series model (released April 2026). Roughly equivalent reasoning quality to `gpt-4o` at slightly lower cost (~$0.04–0.06/run). Both are valid choices.

`gpt-4o` is chosen over `gpt-4.1` purely because it has a longer track record in structured-output and multi-step reasoning benchmarks at the time of writing. Switch to `gpt-4.1` by setting `REASONER_MODEL=gpt-4.1` — no code change needed.

### Option C — `gpt-4o-mini`

Used in Phase 4.2 for one-line summaries. Insufficient for Phase 4.3:
- Structured-output compliance on complex multi-field JSON is less reliable.
- Reasoning depth on borderline policy criteria is weaker — higher hallucination rate on no-evidence cases.
- Rejected as the default; may be used for ablation evals via `REASONER_MODEL=gpt-4o-mini`.

## Consequences

### Positive

- `REASONER_MODEL` env var makes the Reasoner model-agnostic at runtime — contributors with different API access can run evals against their preferred model.
- The Phase 4.3 eval harness explicitly tests two model families (`gpt-4o` vs `gpt-4o-mini`) to quantify the quality delta — this becomes a publishable result for the LinkedIn series.
- `gpt-4o` structured-output compliance means the citation checker (deterministic) operates on well-formed JSON — no prompt-engineering gymnastics needed.

### Negative / risks

- **Cost at eval scale**: ~$2–3 per 30-case eval run. Acceptable; add `REASONER_MODEL=gpt-4o-mini` to `.env` to run a cheap ablation.
- **Latency**: P50 ~8–12s for the full Reasoner call (retrieval + LLM). Within the < 20s eval gate but noticeable in the demo. **Mitigation**: stream the structured output to the demo UI in Phase 4.4.
- **Vendor dependency**: same OpenAI dependency already established by the Phase 4.2 LLM second pass. No new vendor introduced.

### Exit criteria

- `gpt-4.1` or a successor model demonstrably outperforms `gpt-4o` on the Phase 4.3 golden set AND costs the same or less. Switch is a one-line env change.
- An open-weights model (e.g. Llama-3.1-70B-Instruct with structured output) matches `gpt-4o` quality on the golden set AND can run on a contributor's laptop without a GPU. Re-evaluate at Phase 4.5.

---

## Implementation notes

- Env var: `REASONER_MODEL` (default: `gpt-4o`)
- LangChain class: `ChatOpenAI(model=os.getenv("REASONER_MODEL", "gpt-4o"))`
- Response format: `response_format={"type": "json_object"}` + a tight system prompt schema
- The `Decision` Pydantic model (defined in `state.py`) is the schema the LLM must conform to

---

*ADRs are immutable once Accepted. Update the status header only.*
