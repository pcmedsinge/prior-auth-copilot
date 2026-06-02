# docker/hapi — HAPI FHIR server configuration

## IG tarballs

The `igs/` directory is **gitignored**. Before running `make fhir-up` on a fresh checkout, fetch the IG packages:

**Git Bash / WSL2 / macOS / Linux**
```bash
bash docker/hapi/fetch_igs.sh
```

**Windows PowerShell**
```powershell
powershell -ExecutionPolicy Bypass -File docker\hapi\fetch_igs.ps1
```

This downloads two tarballs into `docker/hapi/igs/`:

| File | Version |
|---|---|
| `hl7.fhir.us.core-6.1.0.tgz` | US Core 6.1.0 |
| `hl7.fhir.us.davinci-pas-2.0.1.tgz` | Da Vinci PAS 2.0.1 |

HAPI auto-installs them on first startup (takes ~60s on a cold start).

## application.yaml

Mounts at `/data/hapi/application.yaml` inside the container. Key settings:

- H2 file-based persistence via named Docker volume `prior-auth-hapi-data`
- Validation **disabled on writes** in Phase 4.2 (Synthea output is US-Core-conformant but not PAS-conformant; full validation gates are Phase 4.4)
- Two IGs registered: `hl7.fhir.us.core@6.1.0` and `hl7.fhir.us.davinci-pas@2.0.1`

## Ports

| Host | Container | Service |
|---|---|---|
| `8082` | `8080` | FHIR base URL: `http://localhost:8082/fhir` |

A sibling `payer-fhir` service on port `8090` will be added in Phase 4.4 for the mock PAS `$submit` endpoint.

> **Port rationale**: host port `8082` (not `8080`) is used to avoid conflicts with other local HAPI instances. `8090` is reserved for Phase 4.4.
