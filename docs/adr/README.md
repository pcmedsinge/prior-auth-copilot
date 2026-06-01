# Architecture Decision Records (ADRs)

This folder records the **why** behind every non-trivial architectural choice in the Prior-Auth Co-pilot.

Format: lightweight [MADR-style](https://adr.github.io/madr/) — Context → Decision → Consequences. One file per decision, numbered sequentially, never deleted, only superseded.

## Index

| # | Title | Status |
|---|---|---|
| [0001](0001-langgraph-over-crewai-autogen.md) | Use LangGraph as the agent orchestration framework | Accepted |
| [0002](0002-fhir-server-choice.md) | Local FHIR server choice (HAPI vs Medplum vs Aidbox) | Accepted |

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
