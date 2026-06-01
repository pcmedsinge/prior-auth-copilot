# ADR-0003 — LangGraph state shape (TypedDict vs Pydantic)

- **Status**: Accepted
- **Date**: 2026-06-01
- **Deciders**: Parag Medsinge (tech lead)
- **Supersedes**: —
- **Superseded by**: —

---

## Context

Every LangGraph node in the Prior-Auth Co-pilot reads and writes a shared **graph state** object. By Phase 4.5 that state will carry, at minimum:

- `patient_id`, `service`, `payer_id` (set by Intake)
- `evidence_package` — list of retrieved FHIR resources with refs + tags (set by Evidence Gatherer)
- `decision` — structured `[(criterion, status, evidence_refs, citation)]` (set by Reasoner)
- `bundle` — the assembled Da Vinci PAS Bundle (set by Bundle Builder)
- `review_decision` — approve / edit / send-back (set by Reviewer node via HITL interrupt)
- `submission_response` — payer `ClaimResponse` (set by Submit)
- `trace_id`, `timestamps`, `tool_calls[]` — for the eval harness and audit Provenance

LangGraph supports two idiomatic patterns for state:

- **`TypedDict`** (with `Annotated` reducers) — the LangGraph-native, lightweight pattern.
- **`pydantic.BaseModel`** — runtime validation, richer types, more ceremony.

The choice locks the shape every node code path will use, so making it once now is cheaper than refactoring later. The decision also affects how the **eval harness** (Phase 4.5) serializes traces and how the **LangGraph checkpoint** (Phase 4.4 Reviewer HITL) round-trips state through a persistence layer.

## Decision

**Use `TypedDict` with `Annotated[..., reducer]` fields as the canonical graph-state type.**

Wrap *external boundary* data structures in Pydantic models — `EvidenceItem`, `Decision`, `BundleEnvelope`, `ToolCall` — and reference them by type inside the `TypedDict`. The graph state itself is a `TypedDict`; the leaf values within it can be Pydantic models where validation matters.

In short: **`TypedDict` for the graph state container · Pydantic for the domain values inside it.**

## Options considered

### Option A — `TypedDict` for everything (chosen for the container)

```python
class PAState(TypedDict, total=False):
    patient_id: str
    service: ServiceRequest                      # pydantic model
    evidence: Annotated[list[EvidenceItem], add] # pydantic items + reducer
    decision: Decision | None                    # pydantic model
    bundle: BundleEnvelope | None                # pydantic model
    review_decision: ReviewOutcome | None
    tool_calls: Annotated[list[ToolCall], add]
```

- **Pros**:
  - **LangGraph-native** — `StateGraph(PAState)` is the framework's first-class path; reducers (`Annotated[..., add]`) are designed for `TypedDict`.
  - **Checkpoint round-trip is trivial** — `TypedDict` is just a `dict` at runtime; LangGraph's checkpointers serialize/deserialize without a custom encoder. Phase 4.4's Reviewer interrupt depends on clean checkpointing.
  - **Partial state updates are idiomatic** — a node returns `{"evidence": [...]}` and LangGraph merges it. With Pydantic this requires `.model_copy(update=...)` or a custom reducer per field.
  - **Reducers do exactly what we need** — `Annotated[list[X], add]` for accumulating evidence/tool-calls is one line.
  - **No double-validation** — leaf Pydantic models validate at their construction site; the state container doesn't re-validate on every node transition.
- **Cons**:
  - `TypedDict` keys are not enforced at runtime; a typo in `state["paitient_id"]` silently returns `None`. **Mitigation**: mypy/pyright in CI catches this; never use raw string keys in node code — always go through a typed accessor or destructure at the top of the node.

### Option B — `pydantic.BaseModel` for the entire state

```python
class PAState(BaseModel):
    patient_id: str
    service: ServiceRequest
    evidence: list[EvidenceItem] = []
    decision: Decision | None = None
    ...
```

- **Pros**:
  - Runtime validation on every state mutation.
  - Richer typing (validators, computed fields, JSON schema generation).
  - Single mental model — "everything is a Pydantic model".
- **Cons**:
  - **Fights LangGraph's reducer model** — Pydantic models don't compose with `Annotated[..., add]` naturally; you end up writing custom reducers per field or sub-classing to handle list-merging.
  - **Checkpoint serialization gets noisy** — Pydantic v2 adds metadata to dumps; checkpointers either need a custom encoder or you accept fatter checkpoint blobs. Manageable, but friction we don't need at this scale.
  - **Partial updates are verbose** — every node returns either a full `PAState` or a `model_copy(update=...)`. The framework wants `{"key": value}` dict updates; Pydantic wants object construction. Two mental models in one codebase.
  - **Validation cost on every transition** — negligible at our scale, but a real foot-gun when state grows (every transition re-validates the whole tree).

### Option C — Hybrid (chosen overall)

`TypedDict` for the graph state container; Pydantic models for the domain values inside it.

- **Pros**:
  - Each tool fits its job: `TypedDict` for "this is the contract between nodes" (where LangGraph's idioms apply); Pydantic for "this is a domain value that must be valid" (where the LLM produces or consumes structured data).
  - **Boundary validation where it matters most** — the LLM-emitted `Decision` and `EvidencePackage` get Pydantic-validated at their construction site (rejecting hallucinated shapes early), while the graph state itself stays dict-shaped for LangGraph.
  - **Best fit for eval harness** — `Decision.model_dump()` gives clean JSON for the scorecard; the state dict gives clean LangSmith traces.
- **Cons**:
  - Contributors must internalize "container = TypedDict, leaves = Pydantic". One paragraph in `docs/WORKFLOW.md` will suffice.

### Option D — `dataclasses` with manual reducers

Rejected: no LangGraph reducer support, no validation, worst of both worlds.

## Consequences

### Positive

- LangGraph's `StateGraph`, reducers, checkpointers, and partial-update conventions all work as documented — no fighting the framework.
- Boundary validation lives where the data actually crosses an untrusted boundary (LLM → state, FHIR API → state) — not on every node transition.
- Reviewer HITL checkpointing in Phase 4.4 round-trips cleanly through SQLite/Postgres checkpointers with no custom serializer.
- The eval harness in Phase 4.5 can dump state to JSON for scorecard input with no custom encoder.

### Negative / risks

- **Typo-in-key silent failures**. **Mitigation**: pyright strict mode in CI; every node defines a typed accessor `def get_evidence(state: PAState) -> list[EvidenceItem]:` for any field used in more than one place. Never use raw `state["x"]` outside a 5-line node body.
- **Two mental models** (TypedDict container, Pydantic leaves). **Mitigation**: one paragraph in `docs/WORKFLOW.md` codifies the rule. A `src/state.py` module is the single source of truth for `PAState` + all leaf models — contributors read one file to onboard.
- **Pydantic v2 dependency** is now load-bearing. **Mitigation**: it's already a transitive dep of LangChain/LangGraph; we're not adding surface area.

### Exit criteria (when would we revisit this ADR?)

- LangGraph deprecates `TypedDict` state in favour of a Pydantic-first API (no signal of this as of mid-2026, but track it).
- The state grows beyond ~15 top-level fields and the lack of nested validation produces a real bug class (not a theoretical one). Re-evaluate then.
- A checkpoint backend we want to use cannot serialize `TypedDict` cleanly (not aware of any).

---

## Implementation notes (non-binding — captured here for Issue #5)

Sketch of `src/state.py`:

```python
from typing import Annotated, TypedDict
from operator import add
from pydantic import BaseModel

# --- Leaf domain models (Pydantic — validated at construction) ---

class ServiceRequest(BaseModel):
    code: str            # e.g., "MRI-LUMBAR"
    description: str
    payer_id: str

class EvidenceItem(BaseModel):
    fhir_ref: str        # e.g., "Observation/abc-123" — MUST come from the server, never fabricated
    resource_type: str
    tags: list[str] = [] # deterministic policy-checklist tags
    relevance_note: str | None = None  # LLM-emitted, one line

class Citation(BaseModel):
    policy_id: str
    section: str
    paragraph: str

class CriterionDecision(BaseModel):
    criterion: str
    status: str          # "met" | "not_met" | "unclear"
    evidence_refs: list[str]
    citation: Citation

class Decision(BaseModel):
    criteria: list[CriterionDecision]

class ToolCall(BaseModel):
    tool: str
    args: dict
    result_summary: str
    duration_ms: int

# --- Graph state container (TypedDict — LangGraph-native) ---

class PAState(TypedDict, total=False):
    patient_id: str
    service: ServiceRequest
    evidence: Annotated[list[EvidenceItem], add]
    decision: Decision | None
    bundle: dict | None              # FHIR Bundle as plain dict until Phase 4.4
    review_decision: str | None      # "approve" | "edit" | "send_back"
    tool_calls: Annotated[list[ToolCall], add]
    trace_id: str
```

Conventions every node follows:

1. Destructure inputs at the top: `patient_id = state["patient_id"]`.
2. Return only the **changed** keys: `return {"evidence": [...new items...]}`.
3. Never mutate the input `state` dict in place — return a new dict slice.
4. Pydantic models are constructed only at boundaries (parsing an LLM response, parsing a FHIR response). Inside the graph, pass them around as typed values.

---

*ADRs are immutable once Accepted. Update the status header only.*
