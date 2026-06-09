# Operations Runbook — Prior-Auth Co-pilot

Practical reference for anyone running the system locally or debugging a stuck run.

---

## Quick reference

| Command | What it does |
|---|---|
| `bash start.sh` | Start full stack (first run ~10-15 min) |
| `bash start.sh --no-synthea --no-policies` | Fast restart if data already loaded |
| `bash stop.sh` | Stop all services |
| `make demo-e2e PATIENT=<id>` | Interactive end-to-end demo |
| `make evals` | Run all evals, produce v1.0 scorecard |
| `make evals-fast` | Same, skip LLM calls (deterministic only) |
| `make fhir-reset` | ⚠ Wipe HAPI volumes (full reset) |

---

## Service map

| Service | Port | Start command | Log command |
|---|---|---|---|
| Provider HAPI | 8082 | `make fhir-up` | `make fhir-logs` |
| Payer HAPI | 8090 | `make payer-fhir-up` | `docker compose logs -f payer-fhir` |
| Mock payer (FastAPI) | 8091 | `python scripts/mock_payer.py` | `cat out/mock_payer.log` |
| mcp-fhir SSE | 8084 | `make mcp-up` | `docker compose logs -f mcp-fhir` |

---

## Common failure modes

### `make fhir-up` hangs at the dot loop

**Cause**: HAPI is still loading IGs on first boot. First boot takes 60–90s.  
**Fix**: wait. If it hangs >3 minutes: `docker compose logs fhir | tail -50` — look for Java exceptions.

**Cause**: Port 8082 already in use by another HAPI instance.  
**Fix**: `docker ps` to find the conflicting container; stop it or change `FHIR_BASE_URL` in `.env`.

---

### `make load-synthea` fails at `generate`

**Cause**: Synthea Docker image not built yet.  
**Fix**: `docker compose build synthea` then retry.

**Cause**: `docker/hapi/igs/*.tgz` files missing.  
**Fix**: `bash docker/hapi/fetch_igs.sh`

---

### `make ingest-policies` fails with `OPENAI_API_KEY not set`

**Fix**: Add `OPENAI_API_KEY=sk-...` to `.env` or export it in the shell.

---

### Evidence Gatherer returns 0 results for a patient

**Cause**: Patient was not loaded into HAPI (manifest references a bundle that wasn't POSTed).  
**Fix**: `make load-synthea` (idempotent — re-runs without duplicating).

**Verify**: `curl 'http://localhost:8082/fhir/Patient?_summary=count'` should return 50.

---

### Reasoner returns `policy store error`

**Cause**: LanceDB store not present.  
**Fix**: `make ingest-policies`

**Cause**: Store present but `text-embedding-3-small` embedding was changed.  
**Fix**: `make ingest-policies` (idempotent — drops and recreates).

---

### `$validate` fails on Bundle

**Cause**: Payer HAPI not running.  
**Fix**: `make payer-fhir-up`

**Cause**: Da Vinci PAS IG not loaded in payer HAPI.  
**Fix**: Copy IG tarballs: `cp docker/hapi/igs/*.tgz docker/payer-hapi/igs/` then restart payer HAPI.

**Cause**: Bundle is genuinely non-conformant.  
**Fix**: Inspect `bundle_envelope.validation_issues` in the output JSON.

---

### LangGraph graph stuck at Reviewer interrupt

The graph paused at the Reviewer node waiting for `Command(resume=...)`.

**Inspect the checkpoint**:
```python
import sqlite3, json
conn = sqlite3.connect("data/checkpoints/pa.db")
rows = conn.execute("SELECT thread_id, checkpoint_id FROM checkpoints ORDER BY created_at DESC LIMIT 5").fetchall()
print(rows)
```

**Resume manually**:
```python
from prior_auth_copilot.graph import build_graph, get_checkpointer
from prior_auth_copilot.state import ReviewerAction
from langgraph.types import Command

thread_id = "pa-<patient_id>"
config = {"configurable": {"thread_id": thread_id}}

with get_checkpointer() as saver:
    g = build_graph(checkpointer=saver)
    result = g.invoke(Command(resume=ReviewerAction(action="approve")), config=config)
```

**Wipe a stuck thread**:
```python
conn = sqlite3.connect("data/checkpoints/pa.db")
conn.execute("DELETE FROM checkpoints WHERE thread_id = 'pa-<patient_id>'")
conn.commit()
```

---

### Mock payer not responding

**Check**: `curl http://localhost:8091/health`  
**Start**: `python scripts/mock_payer.py` (or `make mock-payer-up`)  
**Log**: `cat out/mock_payer.log`

The Submit node has a graceful fallback — if the mock payer is unreachable it synthesises a `ClaimResponse` locally. The `submit_result.payer_reference` will be populated either way.

---

## How to add a new payer policy

1. Create `data/policies/<payer>-<policy-id>.md` following the section format in `cms-ncd-220.6.17-mri-spine.md`.
2. Run `make ingest-policies` — the ingestion is incremental (all `.md` files in `data/policies/` are embedded).
3. The Reasoner automatically retrieves chunks from the new policy during semantic search.

---

## How to inspect a LangSmith trace

1. Set `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY=ls__...` in `.env`.
2. Set `LANGCHAIN_PROJECT=prior-auth-copilot`.
3. Run `make demo-e2e` — traces appear at `https://smith.langchain.com`.

---

## Embedding model change rollback

If `OPENAI_EMBED_MODEL` is changed, the existing LanceDB store is invalid (vectors are incompatible).  
**Fix**: `make ingest-policies` — drops and recreates the store with the new model.  
**ADR ref**: ADR-0004 (embedding model) documents the exit criteria.
