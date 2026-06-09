# Prior-Auth Co-pilot — task runner
# Requires: Docker Desktop, GNU make (Git Bash or WSL2 on Windows)
# See docker/hapi/README.md for IG fetch step before first fhir-up.

SHELL := /bin/bash
.DEFAULT_GOAL := help

FHIR_BASE_URL ?= http://localhost:8082/fhir

# ── FHIR server ──────────────────────────────────────────────────────────────

.PHONY: fhir-up
fhir-up: ## Start HAPI FHIR server (waits until /fhir/metadata is healthy)
	docker compose up -d fhir
	@echo "Waiting for HAPI to be ready..."
	@until curl -sf $(FHIR_BASE_URL)/metadata > /dev/null 2>&1; do \
		printf '.'; sleep 5; \
	done
	@echo ""
	@echo "HAPI is ready at $(FHIR_BASE_URL)"

.PHONY: fhir-down
fhir-down: ## Stop the HAPI FHIR server container
	docker compose stop fhir

.PHONY: fhir-logs
fhir-logs: ## Tail HAPI container logs
	docker compose logs -f fhir

.PHONY: fhir-reset
fhir-reset: ## ⚠ Stop HAPI and WIPE the H2 data volume (full reset)
	docker compose down -v
	@echo "Volume prior-auth-hapi-data removed."

# ── MCP server (SSE mode — for MCP Inspector / Phase 4.5+) ───────────────

.PHONY: mcp-up
mcp-up: ## Start mcp-fhir in SSE mode (requires fhir-up first)
	docker compose --profile tools up -d mcp-fhir
	@echo "mcp-fhir SSE endpoint: http://localhost:8084/sse"

.PHONY: mcp-down
mcp-down: ## Stop the mcp-fhir SSE container
	docker compose stop mcp-fhir

# ── Synthea pipeline ─────────────────────────────────────────────────────────

.PHONY: load-synthea
load-synthea: ## Generate, curate, and load ~50 synthetic patients into HAPI
	python scripts/load_synthea.py generate
	python scripts/load_synthea.py curate
	python scripts/load_synthea.py load

.PHONY: load-synthea-fast
load-synthea-fast: ## Curate + load only (skips generation if out/ already populated)
	python scripts/load_synthea.py curate
	python scripts/load_synthea.py load

# ── Verification ─────────────────────────────────────────────────────────────

.PHONY: smoke
smoke: ## Run smoke test against live HAPI (verifies patient count + evidence tags)
	python scripts/smoke_fhir.py

.PHONY: smoke-tools
smoke-tools: ## Verify all 6 evidence-retrieval tools call HAPI without error
	python scripts/smoke_mcp_tools.py

.PHONY: demo-evidence
demo-evidence: ## Run the evidence-retrieval demo for a given patient
	@test -n "$(PATIENT)" || (echo "Usage: make demo-evidence PATIENT=<id>" && exit 1)
	python scripts/demo_evidence.py $(PATIENT)

# ── Tests ───────────────────────────────────────────────────────

.PHONY: test
test: ## Run unit tests (no live HAPI or OpenAI required)
	pytest tests/ -v

# ── Help ──────────────────────────────────────────────────────────────────────

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
