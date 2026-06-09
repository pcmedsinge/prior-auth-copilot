# ADR-0005 — Vector store for the policy corpus

- **Status**: Accepted
- **Date**: 2026-06-09
- **Deciders**: Parag Medsinge (tech lead)
- **Supersedes**: —
- **Superseded by**: —

---

## Context

The policy corpus (CMS NCDs + optional payer LCDs, ~200–1 000 paragraph chunks) must be stored as embedding vectors and queried by the Medical Necessity Reasoner at runtime. The vector store must:

1. Run locally — no new cloud services.
2. Require no additional Docker containers (already running HAPI on port 8082, Synthea on-demand, mcp-fhir on port 8084).
3. Be Apache-2.0 licensed with no commercial-use restrictions.
4. Integrate cleanly with LangChain's `VectorStore` interface (already a transitive dep via LangGraph).
5. Scale adequately for the project's corpus (< 10 000 chunks through Phase 4.5).

Four options were evaluated.

## Decision

**Use LanceDB (embedded mode, local file) as the vector store.**

Data directory: `data/policy-store/` (gitignored; rebuilt by `make ingest-policies`).  
LangChain integration: `langchain-community` `LanceDB` vectorstore class.

## Options considered

### Option A — LanceDB (chosen)

Columnar embedded vector database. Runs fully in-process; data stored as Arrow/Lance files on disk. Apache-2.0.

- **Pros**:
  - **Zero new infrastructure** — no Docker service, no port, no daemon. `pip install lancedb` is the entire setup.
  - **Local files** — `data/policy-store/` is committed as a gitignored directory; contributors rebuild with one command.
  - **LangChain vectorstore interface** — drop-in compatible; switching to Qdrant/pgvector later is a 3-line config change.
  - **Performance** is more than adequate for < 10 000 chunks — sub-millisecond ANN search.
  - **Apache-2.0** — no license surprises for contributors or commercial adopters.
  - **Reproducibility** — vector store content is deterministic given the same corpus + embedding model version; `make ingest-policies` rebuilds it from scratch.
- **Cons**:
  - Embedded mode means no multi-process concurrent writes. **Non-issue**: ingestion runs once; queries are read-only at inference time.
  - Less community visibility than Chroma or Qdrant among ML practitioners. **Mitigation**: LangChain's `LanceDB` integration is first-class; documentation is adequate.

### Option B — Qdrant

Production-grade, best ANN performance, excellent filtering. But requires a Docker container (new port, new service to start/stop). Overkill for < 10 000 chunks. Rejected on infra-complexity grounds.

### Option C — pgvector (Postgres extension)

Mature, SQL-queryable, great for complex metadata filtering. Requires Postgres + extension — significant infra footprint relative to a 500-chunk corpus. Rejected.

### Option D — ChromaDB

Popular, Python-native, easy to get started. Performance at scale is weaker than LanceDB; Chroma's persistent mode has had stability regressions in prior releases. LanceDB is a better default for a greenfield project at this scale.

## Consequences

### Positive

- `make ingest-policies` is the single command to build or rebuild the vector store. Contributors don't need to manage a running database service.
- `data/policy-store/` is fully reproducible from the raw policy corpus files committed under `data/policies/`.
- LangChain's `LanceDB` integration means the Reasoner node uses the same `VectorStore.similarity_search()` interface as every other LangChain vectorstore — trivial to swap if needed.
- Apache-2.0 across the entire data plane (HAPI + Synthea + LanceDB).

### Negative / risks

- **Not network-accessible** — no REST API for ad-hoc exploration. **Mitigation**: not required; all queries go through the LangGraph node. If ad-hoc exploration is needed, a LanceDB CLI or a simple Jupyter cell suffices.
- **Concurrent write limitation** — only one process may write at a time. **Non-issue** at this scale; `make ingest-policies` is a one-shot offline job.

### Exit criteria

- The corpus grows beyond 50 000 chunks AND query latency becomes a bottleneck — at that point migrate to Qdrant with `docker compose up qdrant`.
- Multi-tenant / multi-user scenarios emerge that require a networked vector store.

---

## Implementation notes

- Package: `lancedb>=0.8.0` + `langchain-community>=0.2.0`
- Data dir: `data/policy-store/` (gitignored; rebuilt by `make ingest-policies`)
- Embedding model: `text-embedding-3-small` (ADR-0004)
- Table name: `policy_chunks`
- Metadata columns: `policy_id`, `section`, `paragraph_index`, `source_url`, `chunk_hash`

---

*ADRs are immutable once Accepted. Update the status header only.*
