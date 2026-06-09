# ADR-0008 — LangGraph checkpoint persistence backend

- **Status**: Accepted
- **Date**: 2026-06-09
- **Deciders**: Parag Medsinge (tech lead)
- **Supersedes**: —
- **Superseded by**: —

---

## Context

Phase 4.4 introduces a LangGraph `interrupt()` checkpoint at the Reviewer node. When the graph pauses, the full `PAState` (evidence package, Decision, draft Bundle) must be persisted so:

1. The Reviewer can read it — potentially minutes or hours later.
2. The graph can resume exactly where it left off when the Reviewer acts.
3. Each run produces an immutable audit record (required by the Phase 4.4 DoD: every Bundle traceable to the originating checkpoint).

LangGraph's checkpointer interface (`BaseCheckpointSaver`) supports multiple backends. Three were evaluated.

## Decision

**Use `SqliteSaver` (LangGraph built-in) with a local SQLite file at `data/checkpoints/pa.db`.**

The file is gitignored and created automatically on first run.

## Options considered

### Option A — `SqliteSaver` (chosen)

`langgraph.checkpoint.sqlite.SqliteSaver` — ships with LangGraph, zero config, writes to a local SQLite file.

- **Pros**:
  - **Zero new infrastructure** — no new Docker container, no new port, no daemon.
  - **Built-in to LangGraph** — `SqliteSaver` is the reference checkpointer; all LangGraph checkpoint semantics (thread ID, config, step) are first-class.
  - **Fully queryable audit trail** — `data/checkpoints/pa.db` is a standard SQLite file; any SQLite viewer can inspect checkpoint history.
  - **Deterministic across runs** — each invocation gets a stable `thread_id` derived from `patient_id` + timestamp, so resume is unambiguous.
  - **Reproducible** — `data/checkpoints/` is gitignored; contributors start clean on each checkout.
- **Cons**:
  - **Single-writer limitation** — SQLite is not suitable for multi-user concurrent writes. **Non-issue** at this scale (one demo user at a time).
  - **No built-in TTL / expiry** — checkpoints accumulate unless pruned. **Mitigation**: `make clean-checkpoints` target; not critical for a demo.

### Option B — `PostgresSaver`

Production-grade, concurrent, queryable via SQL. Requires a Postgres container — yet another Docker service alongside HAPI (8082), payer HAPI (8090), mcp-fhir (8084). Overkill for local dev.

### Option C — `MemorySaver`

Built-in to LangGraph, in-process, zero config. But state is lost on process exit — the Reviewer interrupt would require the reviewer to act before the Python process terminates. Unusable for a realistic HITL demo.

## Consequences

### Positive

- `make demo-e2e` creates `data/checkpoints/pa.db` on first run — no setup step.
- Every checkpoint is addressable by `thread_id` + `checkpoint_id` — the `Provenance` resource in the Bundle stores these, satisfying the audit trail DoD.
- `SqliteSaver` uses SQLite's WAL mode — safe to query the file while the graph is paused.

### Negative / risks

- **SQLite single-writer** — not a real constraint at demo scale.
- **Accumulating checkpoint file** — `make clean-checkpoints` is the escape hatch; document in the quick-start.

### Exit criteria

Revisit when the project needs multi-user concurrent PA workflows or a shared deployment. At that point the migration is a one-line swap to `PostgresSaver`.

---

## Implementation notes

- File: `data/checkpoints/pa.db` (gitignored)
- `thread_id`: `f"pa-{patient_id}"` — stable, human-readable, one thread per patient
- `SqliteSaver` is passed to `StateGraph.compile(checkpointer=saver)`

---

*ADRs are immutable once Accepted. Update the status header only.*
