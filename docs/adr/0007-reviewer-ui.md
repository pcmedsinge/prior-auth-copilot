# ADR-0007 — Reviewer UI surface for the HITL checkpoint

- **Status**: Accepted
- **Date**: 2026-06-09
- **Deciders**: Parag Medsinge (tech lead)
- **Supersedes**: —
- **Superseded by**: —

---

## Context

Phase 4.4 introduces a human-in-the-loop Reviewer step before any PA Bundle is submitted to the payer. The Reviewer must be able to:

1. **Read** the draft PAS Bundle (human-readable view), the Reasoner's Decision + citations, and the underlying FHIR evidence references.
2. **Act** — one of three choices: approve (resume graph → submit), edit (modify justification text, re-validate), or send back (write feedback, replay Reasoner).
3. **Do this from a fresh terminal** — no browser tab to open, no port to remember, no separate process to start.

For v1.0 the reviewer is a developer or UM nurse running the demo locally. The UI must record well in a 90-second Loom video and not require any browser.

Three options were evaluated.

## Decision

**Use a `rich`-powered interactive CLI as the Reviewer UI.**

A `rich` `Panel` renders the Decision summary + Bundle metadata in colour. `typer` or a simple `input()` prompt captures the three reviewer actions. Zero new runtime dependencies beyond `rich` (which is already a transitive dep of many Python tools).

## Options considered

### Option A — `rich` CLI (chosen)

- **Pros**:
  - **Zero new infra** — no long-running process, no port, no browser.
  - **Loom-friendly** — terminal recording captures full reviewer interaction; colour output from `rich` is visually clear.
  - **One dependency** — `rich` is already in the Python ecosystem; many contributors have it installed.
  - **LangGraph `interrupt()` fits naturally** — the graph pauses, the CLI collects the reviewer action, the graph resumes via `.invoke(Command(resume=...))`.
  - **Fast to build** — `Panel`, `Table`, `Prompt.ask()` — a working reviewer UI in ~60 lines.
- **Cons**:
  - Not accessible to non-technical users without a terminal.
  - No persistent review history UI (each run is ephemeral).

### Option B — Streamlit

- **Pros**: polished web UI, hot-reload, good for demos to non-technical stakeholders.
- **Cons**: requires a long-running `streamlit run` process alongside the LangGraph graph; thread-safety with LangGraph's async model adds friction; adds ~30MB of deps.

### Option C — React (minimal)

- **Pros**: production-grade, extensible.
- **Cons**: requires a separate `npm` project, build tooling, a dev server — significant scaffolding for what is a demo UI. Phase 4.4 is not the right time.

## Consequences

### Positive

- `make demo-e2e` runs entirely in a terminal — no second window, no port conflict.
- The Loom video records a clean, colour-formatted terminal session.
- `rich` is a zero-cost dependency for contributors.

### Negative / risks

- **Not accessible without a terminal**. **Mitigation**: v1.0 audience is engineers and technically literate UM nurses; this is explicitly a reference implementation, not a production product.
- **No persistent review history**. **Mitigation**: the LangGraph SQLite checkpoint records every state; a contributor can inspect past reviews via the checkpoint database.

### Exit criteria

Revisit when the repo ships a Phase 4.5+ frontend or when a non-terminal stakeholder demo is needed.

---

*ADRs are immutable once Accepted. Update the status header only.*
