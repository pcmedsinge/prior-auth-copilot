#!/usr/bin/env bash
# stop.sh — gracefully shut down the full Prior-Auth Co-pilot stack.
#
# Stops (in order):
#   1. FastAPI mock payer process (if started by start.sh)
#   2. Payer HAPI container (port 8090)
#   3. Provider HAPI container (port 8082)
#   4. mcp-fhir container (if running)
#
# Data is NOT deleted — volumes and out/ are preserved.
# To wipe all data:  make fhir-reset  (destructive, asks confirmation)
#
# Usage:
#   bash stop.sh
# ---------------------------------------------------------------------------
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${REPO_ROOT}"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[stop]${NC} $1"; }
warn() { echo -e "${YELLOW}[warn]${NC} $1"; }

# ── 1. Mock payer ─────────────────────────────────────────────────────────────
PID_FILE="${REPO_ROOT}/out/mock_payer.pid"
if [[ -f "${PID_FILE}" ]]; then
  MOCK_PID=$(cat "${PID_FILE}")
  if kill -0 "${MOCK_PID}" 2>/dev/null; then
    log "Stopping mock payer (PID ${MOCK_PID}) ..."
    kill "${MOCK_PID}" && rm -f "${PID_FILE}"
    log "  Mock payer stopped."
  else
    warn "Mock payer PID ${MOCK_PID} not running — cleaning up PID file."
    rm -f "${PID_FILE}"
  fi
else
  # Try to kill by port if no PID file
  MOCK_PORT="${MOCK_PAYER_PORT:-8091}"
  FOUND_PID=$(lsof -ti :"${MOCK_PORT}" 2>/dev/null || true)
  if [[ -n "${FOUND_PID}" ]]; then
    log "Stopping mock payer on port ${MOCK_PORT} (PID ${FOUND_PID}) ..."
    kill "${FOUND_PID}" 2>/dev/null || true
    log "  Mock payer stopped."
  else
    warn "Mock payer not found — skipping."
  fi
fi

# ── 2. Payer HAPI ─────────────────────────────────────────────────────────────
log "Stopping payer HAPI (port 8090) ..."
docker compose stop payer-fhir 2>/dev/null && log "  Payer HAPI stopped." || warn "  Payer HAPI was not running."

# ── 3. Provider HAPI ──────────────────────────────────────────────────────────
log "Stopping provider HAPI (port 8082) ..."
docker compose stop fhir 2>/dev/null && log "  Provider HAPI stopped." || warn "  Provider HAPI was not running."

# ── 4. mcp-fhir ───────────────────────────────────────────────────────────────
if docker ps --format '{{.Names}}' | grep -q "prior-auth-mcp-fhir" 2>/dev/null; then
  log "Stopping mcp-fhir ..."
  docker compose stop mcp-fhir && log "  mcp-fhir stopped."
fi

echo ""
echo -e "${GREEN}Stack stopped.${NC}"
echo "  Data preserved in Docker volumes and out/ directory."
echo "  To restart:   bash start.sh --no-synthea --no-policies"
echo "  To wipe all:  make fhir-reset"
echo ""
