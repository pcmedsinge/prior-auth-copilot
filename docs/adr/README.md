# Architecture Decision Records (ADRs)

This folder records the **why** behind every non-trivial architectural choice in the Prior-Auth Co-pilot.

Format: lightweight [MADR-style](https://adr.github.io/madr/) — Context → Decision → Consequences. One file per decision, numbered sequentially, never deleted, only superseded.

## Index

| # | Title | Status |
|---|---|---|
| [0001](0001-langgraph-over-crewai-autogen.md) | Use LangGraph as the agent orchestration framework | Accepted |
| [0002](0002-fhir-server-choice.md) | Local FHIR server choice (HAPI vs Medplum vs Aidbox) | Accepted |
| [0003](0003-langgraph-state-shape.md) | LangGraph state shape (TypedDict container, Pydantic leaves) | Accepted |
| [0004](0004-embedding-model.md) | Embedding model for the policy corpus (`text-embedding-3-small`) | Accepted |
| [0005](0005-vector-store.md) | Vector store for the policy corpus (LanceDB embedded) | Accepted |
| [0006](0006-reasoner-llm.md) | LLM for the Medical Necessity Reasoner (`gpt-4o`) | Accepted |

## When to write an ADR

Write one when:
- A choice locks the system into a vendor, standard, or paradigm for >1 quarter.
- A reader 6 months from now would reasonably ask "why did we do it this way?".
- The chosen option was non-obvious — i.e., a credible alternative exists.

Do **not** write one for:
- Library upgrades.
- Bugfixes.
- Cosmetic refactors.

## Lifecycle

`Proposed` → `Accepted` → (`Superseded by ADR-NNNN` | `Deprecated`). Never edit an Accepted ADR except to update its status header.
