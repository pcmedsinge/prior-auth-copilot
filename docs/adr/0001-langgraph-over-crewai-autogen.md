# ADR-0001 — Use LangGraph as the agent orchestration framework

- **Status**: Accepted
- **Date**: 2026-05-30
- **Deciders**: Parag Medsinge (tech lead)
- **Supersedes**: —
- **Superseded by**: —

---

## Context

The Prior-Auth Co-pilot is a multi-step agentic workflow:

```
Intake → Evidence Gatherer → Medical Necessity Reasoner → PAS Bundle Builder → Reviewer (HITL) → Submit
```

Each step has distinct concerns:
- Some steps are deterministic (Bundle assembly, `$validate` calls).
- Some are LLM-mediated with tool-calls (Evidence Gatherer).
- Some are LLM-mediated with RAG (Reasoner).
- One step is explicitly **human-in-the-loop** (Reviewer) and must support pause/resume across an arbitrary wall-clock gap (a UM nurse may take minutes or hours to approve).

We need an orchestration framework that gives us:

1. **Explicit graph topology** (not implicit prompt-chain magic) — for auditability in a regulated workflow.
2. **First-class human-in-the-loop / interrupt support** — pause state, resume on approval.
3. **Persistable state** — every agent decision and tool call must be replayable for audit.
4. **Streaming + observability hooks** — we need to wire traces into the eval harness from day 1.
5. **Stable enough to bet on for ~12 months** without weekly breaking changes.

Three credible candidates were considered: **LangGraph**, **CrewAI**, **AutoGen**.

## Decision

**Use LangGraph.**

## Options considered

### Option A — LangGraph (chosen)

- **Pros**:
  - Explicit `StateGraph` with typed state — matches our need for an auditable graph.
  - Built-in **checkpointing** and **interrupt** / **resume** — directly maps to the Reviewer HITL step.
  - LangSmith integration gives us tracing for the eval harness for free.
  - Mature tool-calling primitives with deterministic routing (conditional edges).
  - Backed by LangChain Inc. — likely to be around for the 12-month horizon.
- **Cons**:
  - Pulls in the LangChain dependency surface (we mitigate by depending only on `langgraph` + `langchain-core`, not the full `langchain` meta-package).
  - API has churned in the past; we pin a minor version and gate upgrades through an ADR.

### Option B — CrewAI

- **Pros**: Simpler mental model (Crew of Agents with Roles); fast to demo.
- **Cons**:
  - Role/task abstraction is a **leaky metaphor** for our use case — our nodes are workflow stages, not "agents with personas".
  - HITL support is bolted on, not first-class.
  - Less mature checkpointing/replay story — a real problem for audit.
  - Optimized for "crew of generalist agents collaborating", which is *not* our shape.

### Option C — AutoGen

- **Pros**: Strong research backing (Microsoft); good multi-agent conversation patterns.
- **Cons**:
  - Conversation-centric model is a poor fit for a deterministic-where-possible regulated workflow.
  - v0.4 rewrite introduced significant API churn; framework stability is uncertain on our timeline.
  - HITL exists but is conversational ("ask the human a question"), not workflow-stage ("pause the graph until approval").

### Option D — Hand-rolled state machine + raw model SDKs

- **Pros**: Zero framework lock-in; maximum control.
- **Cons**:
  - We'd rebuild checkpointing, tracing, and tool-call routing from scratch. That work is non-differentiated.
  - LangGraph already gives us 80% of this with a credible exit path (the graph itself is plain Python; we could swap orchestrators in a future ADR).

## Consequences

### Positive

- HITL Reviewer step maps to a single `interrupt()` call — no custom queue, no custom state store at MVP.
- Every agent run is checkpointed → replay-for-audit comes for free.
- LangSmith traces flow directly into the Phase 4.5 evals harness.
- Aligns with patterns already proven in [`cds-hooks-langgraph-agent`](https://github.com/pcmedsinge/cds-hooks-langgraph-agent) — code and lessons reuse.

### Negative / risks

- LangChain ecosystem dependency surface. **Mitigation**: depend on `langgraph` + `langchain-core` only; never `langchain` meta-package.
- API churn risk. **Mitigation**: pin minor version in `pyproject.toml`; upgrades require an ADR amendment.
- Vendor-coupling temptation with LangSmith. **Mitigation**: tracing exporter is abstracted; OpenTelemetry-compatible exporter is the contractual interface, LangSmith is one implementation.

### Exit criteria (when would we revisit this ADR?)

- LangGraph introduces a breaking change to checkpointing or interrupt semantics.
- A credible competitor ships first-class HL7 FHIR / Da Vinci integration patterns.
- The graph grows beyond ~15 nodes and the StateGraph abstraction starts to fight us (at which point we'd consider a workflow engine like Temporal underneath, with LangGraph as the agent layer only).

---

*ADRs are immutable once Accepted. Update the status header only.*
