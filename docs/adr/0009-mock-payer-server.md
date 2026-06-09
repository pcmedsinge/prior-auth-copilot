# ADR-0009 — Mock payer PAS $submit endpoint

- **Status**: Accepted
- **Date**: 2026-06-09
- **Deciders**: Parag Medsinge (tech lead)
- **Supersedes**: —
- **Superseded by**: —

---

## Context

Phase 4.4 requires a mock payer-side endpoint that:

1. Accepts a Da Vinci PAS-profiled FHIR `Bundle` via `POST /fhir/Claim/$submit`.
2. Validates the Bundle against the `davinci-pas` profile (`$validate`).
3. Returns a mock `ClaimResponse` (approve or deny based on the Bundle's content).

ADR-0002 (FHIR server choice) explicitly reserved port 8090 for this role and noted that "the same image can act as the PAS submission endpoint in Phase 4.4 with a different profile bundle loaded." This ADR documents that decision as accepted.

Two options were evaluated.

## Decision

**Use a second `hapiproject/hapi:v7.4.0` instance (`payer-fhir`) on port 8090 as the mock payer endpoint.**

A custom FastAPI wrapper script (`scripts/mock_payer.py`) intercepts `$submit` POSTs, stores the submitted Bundle, runs `$validate` against the Da Vinci PAS profile, and returns a synthetic `ClaimResponse`.

## Options considered

### Option A — HAPI + FastAPI wrapper (chosen)

- **Pros**:
  - **Reuses the existing HAPI image** — same technology as the provider FHIR server (port 8082). One technology to understand, document, and support.
  - **Real `$validate` against `davinci-pas`** — the profile-validation gate is the highest-value capability; a custom mock server cannot replicate it. HAPI does it natively.
  - **FastAPI wrapper is thin** — ~80 lines that translate `$submit` semantics to standard FHIR REST + a synthetic `ClaimResponse` generator. No new framework knowledge needed.
  - **Already planned in ADR-0002** — port 8090 is reserved, compose service name `payer-fhir` is reserved. This ADR just formalises what was already the plan.
  - **Docker Compose sibling service** — `payer-fhir` starts with `make fhir-up` (or optionally `--profile payer`) and is available at `http://localhost:8090/fhir`.
- **Cons**:
  - **Two HAPI instances** — ~1GB RAM total on the host. Within the "runs on a laptop" constraint.
  - **No real payer PA logic** — ClaimResponse is synthetic (always approve if validation passes). **Expected**: this is explicitly a mock for demo purposes.

### Option B — Custom FastAPI mock server only

Build a FastAPI app that mimics `$submit` without HAPI. Faster to start, but loses the `$validate` conformance gate — which is a core Phase 4.4 DoD requirement ("Zero Bundles emitted that fail `$validate`"). Rejected.

### Option C — Inferno PAS test kit (stretch goal only)

The HL7 Inferno PAS test kit provides a full PAS compliance test suite. Excellent for Phase 4.5 release testing. Too heavyweight for Phase 4.4 local dev. Reserved as a Phase 4.5 stretch goal.

## Consequences

### Positive

- `$validate` against `davinci-pas` on the payer side gives the Bundle Builder a real conformance gate: a non-conformant Bundle is rejected before it would reach a real payer.
- One-image, two-role pattern — contributors only learn one FHIR server technology.
- The `ClaimResponse` returned by `scripts/mock_payer.py` is a valid FHIR resource suitable for display in the Reviewer CLI.

### Negative / risks

- **Second HAPI instance cold start** adds ~30–60s to `make fhir-up`. **Mitigation**: healthcheck on `payer-fhir` parallels the `fhir` healthcheck; both must be healthy before `fhir-up` declares ready.
- **Port 8090 in use on the host**. **Mitigation**: documented in `.env.example`; `docker-compose.yml` uses host port 8090 → container port 8080.

---

## Implementation notes

- Compose service: `payer-fhir`, image `hapiproject/hapi:v7.4.0`, port `8090:8080`
- Config: `docker/payer-hapi/application.yaml` (Da Vinci PAS profile loaded, validation strict)
- IG dir: `docker/payer-hapi/igs/` (same tarballs as `docker/hapi/igs/`)
- FHIR base URL: `http://localhost:8090/fhir`
- FastAPI wrapper: `scripts/mock_payer.py` (handles `$submit`, returns `ClaimResponse`)

---

*ADRs are immutable once Accepted. Update the status header only.*
