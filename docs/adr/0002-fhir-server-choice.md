# ADR-0002 — Local FHIR server choice (HAPI vs Medplum vs Aidbox)

- **Status**: Accepted
- **Date**: 2026-06-01
- **Deciders**: Parag Medsinge (tech lead)
- **Supersedes**: —
- **Superseded by**: —

---

## Context

Phase 4.2 needs a FHIR R4 server running locally to host Synthea-generated synthetic patients. The Evidence Gatherer node (via the `fhir-mcp-suite` MCP server) queries this server for `Observation`, `Condition`, `Procedure`, `MedicationRequest`, `ImagingStudy`, and `DocumentReference` resources.

The same server also has to carry the project forward into later phases:

- **Phase 4.3** — host the patient corpus the Reasoner runs against; no new server requirement.
- **Phase 4.4** — needs a server (or a sibling mock) that can act as the **payer-side PAS `$submit` endpoint** and run `$validate` against `us-core` + `davinci-pas` profiles in CI.
- **Phase 4.5** — needs reproducible setup so the v1.0 release demo runs against a fresh `git clone` in <10 minutes on a contributor's laptop.

Constraints that frame the decision:

1. **Local dev on Windows** is the primary target (this workspace). Linux/macOS must also work — contributors won't all be on Windows.
2. **One-command bring-up** — `make fhir-up` or `docker compose up`. No Java/Postgres/Node tooling required on the host.
3. **Truly open-source license** — Apache-2.0 or compatible. No source-available / non-commercial / "community edition" license that bites at adoption time.
4. **US Core + Da Vinci profile support** — at minimum, the server's `$validate` operation must accept these IG packages and produce real conformance verdicts.
5. **Solo-developer scale** — ≤50 patients, <1GB RAM resting. Not a benchmark contest.

Three credible options were considered: **HAPI FHIR JPA Server**, **Medplum**, and **Aidbox**.

## Decision

**Use the HAPI FHIR JPA Server (Docker image: `hapiproject/hapi:latest`) as the local FHIR server for Phase 4.2 onward.**

A second `hapi` instance with PAS-profile validation enabled will play the **mock payer `$submit` endpoint** role in Phase 4.4, configured as a sibling service in the same `docker-compose.yml`.

## Options considered

### Option A — HAPI FHIR JPA Server (chosen)

The reference open-source FHIR R4/R5 server from the HL7 community. Java/Spring under the hood, packaged as a single Docker image with embedded H2 (default) or external Postgres (production).

- **Pros**:
  - **Apache-2.0**, no asterisks. The reference implementation of FHIR; the conformance behaviour is the spec, not a vendor's interpretation.
  - **First-class IG loading** — drop `us-core` and `davinci-pas` package tarballs in a config dir; `$validate` immediately enforces them. This is the single most decision-critical capability for Phase 4.4 / 4.5.
  - **Synthea integration is paved road** — Synthea ships a `--exporter.fhir.upload.url` mode that posts straight to HAPI. No glue code.
  - **One-container bring-up** — `docker run -p 8080:8080 hapiproject/hapi:latest`. Resting at ~500MB RAM with H2; predictable on Windows Docker Desktop.
  - **Mock payer endpoint reuse** — the same image can act as the PAS submission endpoint in Phase 4.4 with a different profile bundle loaded. One technology, two roles.
  - **MCP ecosystem fit** — `fhir-mcp-suite` already speaks plain FHIR REST against HAPI; no adapter work.
  - **Documentation breadth** — every FHIR question has a HAPI answer on Stack Overflow / Zulip. Lowers the bus-factor risk for contributors.
- **Cons**:
  - **Cold-start time** — ~30–60s to load IGs on first boot. Mitigated by `make` target waiting on `/fhir/metadata`.
  - **Developer UX is utilitarian** — no built-in admin console worth speaking of. We don't need one (MCP + curl + the FHIR REST API are enough).
  - **Java/Spring under the hood** — irrelevant to us as users, but bloats the image vs leaner alternatives.

### Option B — Medplum

Modern TypeScript-based FHIR platform. Server + admin console + auth + storage in one stack. Self-host option is free.

- **Pros**:
  - Excellent developer UX — TypeScript SDKs, polished admin console, opinionated patterns for common workflows.
  - Active development; good DX for greenfield apps building *with* Medplum as the platform.
  - Apache-2.0 license on the open-source server.
- **Cons**:
  - **Stack weight at local-dev scale is wrong-shaped** — the self-host bring-up wants Postgres + Redis + the Medplum server + a console container. Multiple moving parts for a workload that's "50 patients on a laptop".
  - **IG / profile validation is less mature than HAPI** — Medplum's profile support exists but is not the reference implementation; Da Vinci PAS conformance gates would be reasoning-about-a-vendor rather than reasoning-about-the-spec.
  - **Architecture pulls us into Medplum's worldview** — auth, identity, custom resources. None of that is on our roadmap. We'd spend time ignoring features.
  - **Mock payer endpoint role** — possible but unnatural; we'd be using Medplum as something it isn't designed to be.

### Option C — Aidbox (Community Edition)

Clojure-based, very fast, mature FHIR R4/R5 implementation. Used in production by serious teams.

- **Pros**:
  - Performance is excellent. AQL-style query expressiveness.
  - Mature `$validate` and profile handling.
- **Cons**:
  - **License is the deal-breaker** — Aidbox Community is **free for non-commercial use only**. Apache-2.0 OSS project that may end up in someone's commercial pilot cannot ship with a Community-Edition dependency. This is a contributor-trust issue, not a personal-use issue.
  - **Smaller community in OSS FHIR reference implementations** — Stack Overflow / GitHub Issue depth is lower than HAPI's.
  - **Vendor-coupled** — a single company controls the roadmap.

### Option D — Roll our own / in-memory FHIR mock

Tempting for 50 patients, but rejected immediately: we lose `$validate` against real IG packages, which is the Phase 4.4 conformance gate. Non-starter.

## Consequences

### Positive

- One Docker image covers the local FHIR server role through Phase 4.3 and (with profile-bundle swap) the mock payer `$submit` role in Phase 4.4. One technology to learn, document, and support.
- `$validate` against `davinci-pas` works out of the box — the gate that protects Phase 4.4's Bundle Builder from emitting non-conformant Bundles depends on this.
- Synthea → HAPI is a paved path; the Phase 4.2 loader script becomes ~20 lines instead of 200.
- Apache-2.0 across the entire data plane — zero license surprises for contributors or commercial adopters.
- HAPI is what the FHIR community itself uses for conformance testing — choosing it aligns the project with industry reference behaviour.

### Negative / risks

- **HAPI cold-start latency** on first boot (~30–60s). **Mitigation**: `make fhir-up` waits on `/fhir/metadata` to return 200 before declaring ready; CI caches the IG-loaded volume between runs.
- **No polished admin UI**. **Mitigation**: not needed — MCP tools + the FHIR REST API + occasional `curl` cover everything in Phase 4.2–4.5. If we ever genuinely need a UI for human inspection, a separate FHIR-browser container (e.g., Inferno) can be added; we don't need to change servers to get one.
- **Java/Spring runtime** is heavier than a TypeScript or Clojure server. **Mitigation**: image is ~700MB compressed, runtime ~500MB RAM — well within "runs on a laptop alongside Docker Desktop + VS Code". Not a real constraint at this scale.
- **HAPI is feature-rich** — easy to lean on non-standard behaviour. **Mitigation**: stick to plain FHIR REST + standard IG operations; never use HAPI-specific extensions in code we ship.

### Exit criteria (when would we revisit this ADR?)

- HAPI's `$validate` against `davinci-pas` proves materially incorrect vs the Inferno PAS test kit, *and* the issue cannot be patched via a newer IG package or HAPI release.
- The project grows to a scale where a single-container H2 instance is genuinely insufficient (>10k patients, multi-user dev). At that point the choice is not HAPI vs Medplum vs Aidbox — it is HAPI-on-H2 vs HAPI-on-Postgres, which is a config change, not an ADR.
- A future Da Vinci IG version requires a server capability HAPI hasn't yet shipped, *and* a competing OSS server has shipped it. Today, HAPI tends to land Da Vinci updates first.

---

## Implementation notes (non-binding — captured here for the engineer picking up Issue #3 / #4)

- Image: `hapiproject/hapi:v7.4.0` (pin a specific version; never `:latest` in committed configs).
- Persistence: H2 (default) for dev; volume-mount the data dir so patient loads survive restarts.
- IG loading: drop `hl7.fhir.us.core` and `hl7.fhir.us.davinci-pas` package tarballs in `docker/hapi/igs/`; HAPI auto-installs on startup.
- Port: `8080` → expose as `8080` on host; FHIR base URL = `http://localhost:8080/fhir`.
- Compose service name: `fhir` (so the MCP server's connection string is `http://fhir:8080/fhir` inside the compose network).
- Sibling service in Phase 4.4: `payer-fhir` on port `8090` with the PAS profile bundle loaded.

---

*ADRs are immutable once Accepted. Update the status header only.*
