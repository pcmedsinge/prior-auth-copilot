# Prior-Auth Co-pilot

> **Open-source, agentic, FHIR-native Prior Authorization co-pilot — built for the CMS-0057 January 2027 mandate.**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Status: Phase 4.3 — Reasoner](https://img.shields.io/badge/status-Phase%204.3%20%C2%B7%20Reasoner-orange.svg)](docs/phases/)
[![FHIR R4](https://img.shields.io/badge/FHIR-R4-red.svg)](https://hl7.org/fhir/R4/)
[![Da Vinci PAS](https://img.shields.io/badge/Da%20Vinci-PAS%20%C2%B7%20CRD%20%C2%B7%20DTR-purple.svg)](https://hl7.org/fhir/us/davinci-pas/)

---

## The problem

Prior Authorization (PA) is the single most-hated workflow in US healthcare — for patients, clinicians, and payers alike.

- The AMA's 2023 PA survey: physicians complete **~43 PA requests per week**, taking an average of **~12 hours** of practice time.
- **~94%** of physicians report PA delays in patient care; **~78%** say PA causes patients to abandon treatment.
- Today most PA traffic moves via fax, phone, and payer portals — a $25B+ annual administrative cost.

**The regulatory forcing function**: The CMS Interoperability and Prior Authorization Final Rule (**CMS-0057-F**) requires impacted payers to implement a **FHIR-based Prior Authorization API** — based on **HL7 Da Vinci PAS / CRD / DTR** — by **January 1, 2027**. Every major payer is scrambling. Provider-side tooling that can *talk* to those APIs barely exists.

This repo is a reference implementation of the provider-side, agentic co-pilot that closes that gap.

---

## What this builds

An agentic system that, given a patient and a proposed service (e.g., MRI lumbar spine, GLP-1 for obesity, advanced cardiac imaging):

1. **Auto-assembles the clinical evidence package** from EHR data via FHIR MCP tools.
2. **Reasons over the payer's medical necessity criteria** (CMS NCDs/LCDs + public payer policies) using RAG.
3. **Drafts the PA request** as a valid **Da Vinci PAS Bundle** (with CRD hooks and DTR-style structured data capture).
4. **Explains the decision** with citations back to specific payer-policy paragraphs.
5. **Routes to a human reviewer** before submission — utilization-management-nurse-in-the-loop by design.

---

## Architecture

```mermaid
flowchart LR
    User([Ordering Provider<br/>or UM Nurse]) --> Intake

    subgraph Agents["LangGraph multi-agent orchestration"]
        Intake[Intake Agent<br/>parse order, identify<br/>service & patient]
        Evidence[Evidence Gatherer<br/>FHIR MCP tools]
        Reasoner[Medical Necessity<br/>Reasoner · RAG over<br/>NCDs/LCDs/policies]
        Builder[PAS Bundle Builder<br/>Da Vinci PAS/CRD/DTR]
        Reviewer[Reviewer Agent<br/>human-in-the-loop]
    end

    Intake --> Evidence --> Reasoner --> Builder --> Reviewer

    subgraph DataPlane["Data plane"]
        FHIR[(FHIR Server<br/>Synthea synthetic<br/>patients)]
        Policies[(Payer Policy KG<br/>CMS NCDs + LCDs +<br/>public payer LCDs)]
        Evals[(Evals harness<br/>tool-call accuracy,<br/>citation grounding)]
    end

    Evidence <--> FHIR
    Reasoner <--> Policies
    Reviewer --> Submit[[Submit to Payer<br/>PAS $submit]]
    Reviewer -.feedback.-> Evals
    Reasoner -.traces.-> Evals
```

### Key building blocks (reuses from existing repos)

| Building block | Reused from |
|---|---|
| FHIR MCP tools for evidence gathering | [`fhir-mcp-suite`](https://github.com/pcmedsinge/fhir-mcp-suite) |
| Payer policy knowledge base | [`FHIRPayerProvider_RCM_Knowledge`](https://github.com/pcmedsinge/FHIRPayerProvider_RCM_Knowledge) |
| FHIR resource construction patterns | [`fhir-mapping-agent`](https://github.com/pcmedsinge/fhir-mapping-agent) |
| Knowledge graph patterns | [`bodhi_app`](https://github.com/pcmedsinge/bodhi_app) |
| LangGraph orchestration patterns | [`cds-hooks-langgraph-agent`](https://github.com/pcmedsinge/cds-hooks-langgraph-agent) |

---

## Status & roadmap

Built in weekly slices. Each slice ships a runnable demo and a LinkedIn write-up.

| Sub-phase | Focus | Status |
|---|---|---|
| [4.1](docs/phases/4.1-problem-framing.md) | Problem framing, repo, architecture, LEADERSHIP.md, ADR-0001 | ✅ Done |
| [4.2](docs/phases/4.2-evidence-retrieval.md) | Synthea data + FHIR MCP evidence retrieval | ✅ Shipped |
| [4.3](docs/phases/4.3-medical-necessity-reasoner.md) | Medical necessity reasoner + RAG over NCDs/LCDs | 🔄 In progress |
| [4.4](docs/phases/4.4-pas-bundle-reviewer.md) | Da Vinci PAS bundle builder + reviewer agent | ⏳ |
| [4.5](docs/phases/4.5-evals-release.md) | Evals harness, outcome metrics, v1.0 release | ⏳ |

Track live progress on the public [GitHub Projects board](https://github.com/users/pcmedsinge/projects) *(link will be live once board is created)*.

---

## Why this matters

This is the reference implementation that lets a 4-person provider-side or payer-side team **stand up a working PA pilot in weeks, not quarters** — against the CMS-0057 deadline. Open source, Apache-2.0, ADR-driven, with evals baked in from day one.

See **[`LEADERSHIP.md`](LEADERSHIP.md)** for how I would lead a squad shipping this for a real payer or provider client — staffing plan, hiring bar, eval gates, and runbook.

---

## Who this is for (personas)

- **Ordering provider** — wants an explainable PA draft, not another portal.
- **Utilization-management nurse** — needs an evidence-traceable, edit-before-submit workflow.
- **Payer reviewer** — receives a clean, standards-compliant PAS Bundle with citations.

Full persona briefs: [`docs/personas/`](docs/personas/).

---

## Repo layout

```
prior-auth-copilot/
├── README.md                          ← you are here
├── LEADERSHIP.md                      ← how I'd lead a squad shipping this
├── LICENSE                            ← Apache-2.0
├── Makefile                           ← fhir-up, load-synthea, smoke, smoke-tools, mcp-up, test, demo-evidence
├── pyproject.toml                     ← Python deps (langgraph, langchain-openai, mcp-fhir, pydantic)
├── docker-compose.yml                 ← HAPI FHIR + Synthea + mcp-fhir services
├── docker/
│   ├── hapi/                          ← HAPI config, IG fetch scripts
│   └── synthea/                       ← Synthea Docker image
├── data/
│   └── synthea-config/
│       ├── modules/low_back_pain.json ← custom GMF module (PA test cases)
│       ├── synthea.properties         ← generation settings
│       ├── seeds.txt                  ← pinned seeds for reproducibility
│       └── manifest.json             ← curated 50-patient set (generated)
├── src/
│   └── prior_auth_copilot/
│       ├── state.py                  ← PAState TypedDict + Pydantic models (ADR-0003)
│       ├── graph.py                  ← LangGraph StateGraph (Intake → Evidence Gatherer)
│       ├── nodes/
│       │   ├── intake.py             ← Intake stub node
│       │   └── evidence_gatherer.py  ← 6 tools + PA checklist + LLM summaries
│       └── evidence/
│           └── tools.py              ← find_observations, find_conditions, etc.
├── scripts/
│   ├── load_synthea.py               ← generate → curate → load pipeline
│   ├── smoke_fhir.py                 ← post-load HAPI verification
│   ├── smoke_mcp_tools.py           ← verify all 6 evidence tools callable
│   └── demo_evidence.py             ← end-to-end evidence demo for one patient
├── tests/
│   └── test_checklist_tagger.py     ← unit tests for PA checklist (no live deps)
├── docs/
│   ├── WORKFLOW.md                   ← how this project is run (read first)
│   ├── mcp-tools.md                  ← evidence tool signatures + examples
│   ├── adr/                          ← Architecture Decision Records
│   ├── personas/                     ← user persona briefs
│   └── phases/                       ← sub-phase plans (4.1 → 4.5)
└── out/                              ← generated Synthea bundles (gitignored)
```

---

## Quick start (Phase 4.2 — Synthea pipeline + Evidence Gatherer)

**Prerequisites**: Docker Desktop running, Git Bash or WSL2 (Windows), Python 3.12+, `OPENAI_API_KEY` set.

```bash
# 1. Fetch IG tarballs (once per checkout)
bash docker/hapi/fetch_igs.sh

# 2. Start the local HAPI FHIR server (waits until healthy)
make fhir-up

# 3. Build the Synthea image, generate ~200 patients, curate 50, load into HAPI
make load-synthea

# 4. Verify HAPI — should print "SMOKE TEST PASSED"
make smoke

# 5. Verify all 6 evidence tools callable
make smoke-tools

# 6. Run unit tests (no live HAPI or OpenAI needed)
make test

# 7. Run the end-to-end evidence demo
#    Get a patient ID from the manifest:
#      python -c "import json; m=json.load(open('data/synthea-config/manifest.json')); print(m['patients'][0]['patient_id'])"
make demo-evidence PATIENT=<patient_id_from_manifest>

# 8. Run the eval harness against all 20 golden cases
make evals-4.2
```

Full pipeline runs from a clean checkout in **< 10 minutes** on Docker Desktop.

> **Windows note**: `make` requires Git Bash or WSL2. Open the terminal in one of those shells before running the commands above.

---

## Author

**Parag Medsinge** — [GitHub @pcmedsinge](https://github.com/pcmedsinge)
