# ADR-0004 — Embedding model for the policy corpus

- **Status**: Accepted
- **Date**: 2026-06-09
- **Deciders**: Parag Medsinge (tech lead)
- **Supersedes**: —
- **Superseded by**: —

---

## Context

Phase 4.3 requires embedding the CMS NCD policy corpus (and optionally 2–3 public payer LCDs) to support semantic retrieval in the Medical Necessity Reasoner. The embedding model must:

1. Run against the OpenAI API — no local inference infrastructure (the same key used in Phase 4.2).
2. Produce embeddings at sufficient quality to distinguish between adjacent policy paragraphs that differ in clinical specificity (e.g. "MRI is covered for radiculopathy" vs "MRI is covered for myelopathy").
3. Be cheap enough for the Phase 4.2 eval gate: < $0.10 per Reasoner run end-to-end.

**Corpus scale**: ~200–500 paragraph-level chunks for the Tier 1 (CMS NCD) corpus; potentially 500–1 000 after Tier 2 payer LCDs are added. This is a small corpus by any measure.

Three credible options were evaluated.

## Decision

**Use `text-embedding-3-small` (OpenAI) as the embedding model.**

Dimension: 1536. Input token limit: 8 191. Priced at ~$0.02 / 1M tokens.

## Options considered

### Option A — `text-embedding-3-small` (chosen)

- **Pros**:
  - **Same API key as the Reasoner LLM** — zero new credentials, zero new client code.
  - Retrieval quality is strong on dense technical/clinical text at paragraph level. OpenAI's MTEB benchmarks show consistent improvement over `ada-002` on retrieval tasks.
  - At 200–500 chunks the entire corpus costs < $0.01 to embed once and is never re-embedded unless policy content changes.
  - `langchain-openai` already present as a dependency — `OpenAIEmbeddings(model="text-embedding-3-small")` is two lines.
- **Cons**:
  - Proprietary API call; embedding vectors cannot be reproduced offline.
  - Not domain-specific (no clinical pre-training).

### Option B — `text-embedding-3-large`

Higher dimension (3 072), higher recall on hard retrieval tasks, ~6× more expensive.
At < 1 000 chunks the quality delta over `3-small` is immeasurable. Rejected on cost grounds.

### Option C — MedCPT (NCBI, open-weights, 768-dim)

Trained on PubMed + clinical trial data; best domain-specific recall in published evals.
Requires local inference (Hugging Face `sentence-transformers`) — adds a new runtime dependency
and makes the project harder to reproduce on a contributor's laptop without a GPU.
Reconsidered at Phase 4.5 if retrieval quality is a bottleneck.

## Consequences

### Positive

- One API key covers both retrieval (embedding) and reasoning (chat completion).
- `langchain-openai` `OpenAIEmbeddings` is already a project dependency — no new package required.
- Cost is negligible at corpus scale; embed-once, query-many pattern.

### Negative / risks

- **Vendor lock** — embedding vectors are tied to OpenAI's model version. If OpenAI deprecates `3-small`, vectors must be re-computed. **Mitigation**: the corpus is small; re-embedding costs < $0.01.
- **No offline reproducibility** — CI evals that run the full RAG pipeline require `OPENAI_API_KEY`. **Mitigation**: the deterministic checklist tagger (already in Phase 4.2) can run without any API key; only the Reasoner second-pass requires it. `--no-llm` mode in the eval runner already models this separation.

### Exit criteria

Revisit if any of the following occur:
- Retrieval recall on the 30-case golden set (Phase 4.3 eval gate) falls below 0.85 with `3-small` but measurably improves with `3-large` or MedCPT.
- The corpus grows beyond 50 000 chunks (at which point domain-specific embedding quality differences become significant).

---

*ADRs are immutable once Accepted. Update the status header only.*
