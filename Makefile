# Prior-Auth Co-pilot — task runner
# Requires: Docker Desktop, GNU make (Git Bash or WSL2 on Windows)
# See docker/hapi/README.md for IG fetch step before first fhir-up.

SHELL := /bin/bash
.DEFAULT_GOAL := help

FHIR_BASE_URL ?= http://localhost:8082/fhir

# ── Full stack start / stop ────────────────────────────────────────────────────

.PHONY: start
start: ## Start the full stack (HAPI + patients + policies + mock payer + smoke test)
	bash start.sh

.PHONY: start-fast
start-fast: ## Fast restart — skip Synthea generation and policy ingestion
	bash start.sh --no-synthea --no-policies

.PHONY: stop
stop: ## Stop all services (HAPI containers + mock payer process)
	bash stop.sh

.PHONY: install
install: ## Install Python dependencies
	pip install -r requirements.txt 2>$$null || pip install python-dotenv requests mcp-fhir httpx langgraph langchain-openai langsmith pydantic structlog lancedb langchain-community pypdf rich fastapi uvicorn langgraph-checkpoint-sqlite

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
	@echo "Volumes prior-auth-hapi-data and prior-auth-payer-hapi-data removed."

# ── Payer mock FHIR server (Phase 4.4) ────────────────────────────────────────

.PHONY: payer-fhir-up
payer-fhir-up: ## Start mock payer HAPI server on port 8090 (waits until healthy)
	docker compose up -d payer-fhir
	@echo "Waiting for payer HAPI to be ready..."
	@until curl -sf http://localhost:8090/fhir/metadata > /dev/null 2>&1; do \
		printf '.'; sleep 5; \
	done
	@echo ""
	@echo "Payer HAPI ready at http://localhost:8090/fhir"

.PHONY: payer-fhir-down
payer-fhir-down: ## Stop the payer HAPI container
	docker compose stop payer-fhir

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

.PHONY: demo-reason
demo-reason: ## Run the full pipeline demo (evidence + reasoning) for a given patient
	@test -n "$(PATIENT)" || (echo "Usage: make demo-reason PATIENT=<id>" && exit 1)
	python scripts/demo_reason.py $(PATIENT)

.PHONY: demo-e2e
demo-e2e: ## Run the full end-to-end demo including HITL reviewer (requires all services)
	@test -n "$(PATIENT)" || (echo "Usage: make demo-e2e PATIENT=<id>" && exit 1)
	python scripts/demo_e2e.py $(PATIENT)

.PHONY: mock-payer-up
mock-payer-up: ## Start the FastAPI mock payer server in the background (port MOCK_PAYER_PORT)
	python scripts/mock_payer.py &

# ── Tests ───────────────────────────────────────────────────────

.PHONY: test
test: ## Run unit tests (no live HAPI or OpenAI required)
	pytest tests/ -v

# ── Evals ─────────────────────────────────────────────────────

.PHONY: evals-4.2
evals-4.2: ## Run Phase 4.2 eval harness (requires fhir-up + load-synthea + OPENAI_API_KEY)
	python evals/runners/run_4_2.py

.PHONY: evals-4.2-no-llm
evals-4.2-no-llm: ## Run Phase 4.2 evals without LLM second pass (faster, deterministic only)
	python evals/runners/run_4_2.py --no-llm

.PHONY: evals-4.2-ci
evals-4.2-ci: ## Run Phase 4.2 evals in CI mode (exits 1 if any target missed)
	python evals/runners/run_4_2.py --ci

.PHONY: evals-4.3
evals-4.3: ## Run Phase 4.3 Reasoner eval harness (requires fhir-up + load-synthea + ingest-policies + OPENAI_API_KEY)
	python evals/runners/run_4_3.py

.PHONY: evals-4.3-ci
evals-4.3-ci: ## Run Phase 4.3 evals in CI mode
	python evals/runners/run_4_3.py --ci

.PHONY: evals-4.4
evals-4.4: ## Run Phase 4.4 Bundle Builder eval harness
	python evals/runners/run_4_4.py

.PHONY: evals
evals: ## Run ALL phase evals and produce the v1.0 combined scorecard
	python evals/runners/run_all.py

.PHONY: evals-ci
evals-ci: ## Run all evals in CI mode (exits 1 if any gate missed)
	python evals/runners/run_all.py --ci

.PHONY: evals-fast
evals-fast: ## Run all evals without LLM second pass (faster, deterministic only)
	python evals/runners/run_all.py --no-llm

# ── Policy corpus ─────────────────────────────────────────────────────────────

.PHONY: ingest-policies
ingest-policies: ## Embed policy corpus into LanceDB (requires OPENAI_API_KEY)
	python scripts/ingest_policies.py

# ── Help ──────────────────────────────────────────────────────────────────────

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
