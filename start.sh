#!/usr/bin/env bash
# start.sh — bring up the full Prior-Auth Co-pilot stack from scratch.
#
# What this does (in order):
#   1. Fetch IG tarballs (skipped if already present)
#   2. Start provider HAPI (port 8082) — waits until healthy
#   3. Start payer HAPI (port 8090)   — waits until healthy
#   4. Build Synthea Docker image (cached after first run)
#   5. Generate + curate + load 50 synthetic patients into provider HAPI
#   6. Embed policy corpus into LanceDB (skipped if store already present)
#   7. Start FastAPI mock payer (port 8091) in background
#   8. Run smoke tests — fails fast if anything is wrong
#
# Usage:
#   bash start.sh            # full start (first checkout: ~10-15 min)
#   bash start.sh --no-synthea  # skip patient generation (uses existing out/)
#   bash start.sh --no-policies # skip policy ingestion (uses existing store)
#
# Prerequisites:
#   Docker Desktop running
#   Python 3.12+ in PATH
#   OPENAI_API_KEY set in .env or environment
#
# Ports used:
#   8082  provider HAPI (EHR / evidence data)
#   8090  payer HAPI   (PAS $validate)
#   8091  mock payer   (FastAPI $submit endpoint)
# ---------------------------------------------------------------------------
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${REPO_ROOT}"

NO_SYNTHEA=false
NO_POLICIES=false

for arg in "$@"; do
  case $arg in
    --no-synthea)  NO_SYNTHEA=true ;;
    --no-policies) NO_POLICIES=true ;;
  esac
done

# Colours
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

log()  { echo -e "${GREEN}[start]${NC} $1"; }
warn() { echo -e "${YELLOW}[warn]${NC} $1"; }
fail() { echo -e "${RED}[error]${NC} $1"; exit 1; }

# ── 1. IG tarballs ────────────────────────────────────────────────────────────
log "Step 1/8 — Checking IG tarballs ..."
HAPI_IGS="docker/hapi/igs"
PAYER_IGS="docker/payer-hapi/igs"

if ls "${HAPI_IGS}"/*.tgz 1>/dev/null 2>&1; then
  log "  IGs already present in ${HAPI_IGS}/ — skipping fetch."
else
  log "  Fetching IGs ..."
  bash docker/hapi/fetch_igs.sh
fi

# Copy (or symlink) IGs to payer-hapi dir if missing
if ! ls "${PAYER_IGS}"/*.tgz 1>/dev/null 2>&1; then
  log "  Copying IGs to ${PAYER_IGS}/ ..."
  cp "${HAPI_IGS}"/*.tgz "${PAYER_IGS}/" 2>/dev/null || warn "  Could not copy IGs to payer dir — fetch manually if payer-fhir fails."
fi

# ── 2. Provider HAPI ──────────────────────────────────────────────────────────
log "Step 2/8 — Starting provider HAPI (port 8082) ..."
docker compose up -d fhir
echo -n "  Waiting"
until curl -sf http://localhost:8082/fhir/metadata >/dev/null 2>&1; do
  printf '.'
  sleep 5
done
echo ""
log "  Provider HAPI ready."

# ── 3. Payer HAPI ─────────────────────────────────────────────────────────────
log "Step 3/8 — Starting payer HAPI (port 8090) ..."
docker compose up -d payer-fhir
echo -n "  Waiting"
until curl -sf http://localhost:8090/fhir/metadata >/dev/null 2>&1; do
  printf '.'
  sleep 5
done
echo ""
log "  Payer HAPI ready."

# ── 4. Build Synthea image ────────────────────────────────────────────────────
log "Step 4/8 — Building Synthea Docker image (cached after first run) ..."
docker compose build synthea

# ── 5. Synthea pipeline ───────────────────────────────────────────────────────
if [[ "${NO_SYNTHEA}" == "true" ]]; then
  warn "Step 5/8 — Skipping Synthea generation (--no-synthea). Using existing out/ data."
  python scripts/load_synthea.py curate
  python scripts/load_synthea.py load
else
  log "Step 5/8 — Generating, curating, and loading 50 synthetic patients ..."
  python scripts/load_synthea.py generate
  python scripts/load_synthea.py curate
  python scripts/load_synthea.py load
fi

# ── 6. Policy corpus ──────────────────────────────────────────────────────────
POLICY_STORE="data/policy-store"
if [[ "${NO_POLICIES}" == "true" ]]; then
  warn "Step 6/8 — Skipping policy ingestion (--no-policies)."
elif [[ -d "${POLICY_STORE}" ]] && ls "${POLICY_STORE}"/*.lance 1>/dev/null 2>&1; then
  log "Step 6/8 — Policy store already present — skipping ingestion."
  log "  (Re-run: python scripts/ingest_policies.py)"
else
  log "Step 6/8 — Embedding policy corpus into LanceDB ..."
  python scripts/ingest_policies.py
fi

# ── 7. Mock payer ─────────────────────────────────────────────────────────────
log "Step 7/8 — Starting FastAPI mock payer (port 8091) ..."
MOCK_PAYER_PORT="${MOCK_PAYER_PORT:-8091}"
if curl -sf "http://localhost:${MOCK_PAYER_PORT}/health" >/dev/null 2>&1; then
  warn "  Mock payer already running on port ${MOCK_PAYER_PORT}."
else
  nohup python scripts/mock_payer.py >"${REPO_ROOT}/out/mock_payer.log" 2>&1 &
  MOCK_PID=$!
  echo "${MOCK_PID}" > "${REPO_ROOT}/out/mock_payer.pid"
  sleep 2
  if curl -sf "http://localhost:${MOCK_PAYER_PORT}/health" >/dev/null 2>&1; then
    log "  Mock payer started (PID ${MOCK_PID})."
  else
    warn "  Mock payer may not be running — check out/mock_payer.log"
  fi
fi

# ── 8. Smoke tests ────────────────────────────────────────────────────────────
log "Step 8/8 — Running smoke tests ..."
python scripts/smoke_fhir.py && log "  smoke_fhir: PASSED" || fail "  smoke_fhir: FAILED"
python scripts/smoke_mcp_tools.py && log "  smoke_mcp_tools: PASSED" || warn "  smoke_mcp_tools: check output above"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Stack is ready.${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "  Provider HAPI  : http://localhost:8082/fhir"
echo "  Payer HAPI     : http://localhost:8090/fhir"
echo "  Mock payer     : http://localhost:8091"
echo ""
echo "  Run the end-to-end demo:"
PATIENT_ID=$(python -c "import json; m=json.load(open('data/synthea-config/manifest.json')); print(m['patients'][0]['patient_id'])" 2>/dev/null || echo "<patient_id>")
echo "    make demo-e2e PATIENT=${PATIENT_ID}"
echo ""
echo "  Run all evals:"
echo "    make evals"
echo ""
echo "  To stop everything:  bash stop.sh"
echo ""
