# Healthcare AI Repositioning Plan — Parag Medsinge (@pcmedsinge)

**Last updated**: May 2026
**Current focus**: Phase 4 — Flagship #1: Agentic Prior-Auth Co-pilot
**This workspace**: `E:\PracticeApps\AIRelated\PriorAuthCopilot`
**Ideation workspace**: `E:\PracticeApps\AIRelated\IdeasHome`

---

## Overall progress

| Phase | Description | Status |
|---|---|---|
| Resume | 6 changes applied (Word doc) | ✅ Complete |
| LinkedIn | Headline + About + Experience updated | ✅ Complete |
| Naukri | Headline + Summary + Current role + Skills updated | ✅ Complete |
| Phase 1 | GitHub Profile README rewrite (6 changes) | ✅ Complete · commit 011bb0c |
| Phase 2 | Repo hygiene (renames, topic fixes, 12 archives) | ✅ Complete |
| Phase 3 | README polish for top 6 pinned repos | ⏳ Pending (can run in parallel with Phase 4) |
| **Phase 4** | **Flagship #1: Prior-Auth Co-pilot build** | ▶ IN PROGRESS — start here |
| Phase 5 | Flagship #2: Clinical LLM Quality Harness | ⏳ Start Week 4 in parallel |
| Phase 6 | LinkedIn content rhythm (2 posts/week) | ⏳ Continuous from Week 2 |

---

## Target outcome

Land a **Healthcare AI Solutions Architect / Technical Leader / Fractional Advisory** role at the AI × healthcare intersection. Mid-size healthcare-AI startups, GCCs, EHR vendors, FHIR/MCP/LangChain platform vendors.

**Explicitly avoid**: roles that screen with live algorithm coding (FAANG SWE ladders, generic "Senior Engineer" listings).

**Time budget**: 6–8 hrs/day, 6–8 week sprint.

---

## User background (locked facts)

- **Parag Medsinge** · GitHub @pcmedsinge · LinkedIn linkedin.com/in/paragmedsinge · Pune, India
- Long career healthcare IT · 16.5 yrs Altera Digital Health (formerly Allscripts) as Manager–Product Development
- Led product development on **Sunrise Clinical Manager, Sunrise Surgery, and adjacent products** with teams of **30+ engineers across multiple geographies**
- Since **March 2025**: full-time independent — FHIR (payer-side), openEHR, MCP, agentic LLM workflows, Radiology AI (lung disease + breast cancer) for NDA'd startup
- Key metric: **69.8% BP control rate on 279-patient synthetic cohort** (Pramana / fhir-dqm-engine)
- Tech stack: HL7 FHIR R4/R5, Da Vinci IGs (PAS/CRD/DTR/PDex/Drug Formulary/Plan-Net/BCDA), openEHR (CKM, EHRbase, AQL), MCP, LangGraph, LangChain, NVIDIA MONAI, MedGemma, DICOM, Orthanc PACS, OHIF, Neo4j, FastAPI, React, C#/.NET, Python, TypeScript, GitHub Copilot, Claude Code

---

## Critical positioning rules (locked — apply on ALL surfaces)

### Forbidden everywhere:
- "hands-on developer / coder," "writes code daily," "full-stack engineer" (LeetCode trigger)
- "AI Engineering Leader," "Engineering Leader" (framework-mastery expectation)
- "Veteran" / "X+ years of …" (ages badly)
- "Founding Engineer" (live-coding screen trigger)
- "intensive self-directed phase," "limited fractional," "sandbox-based not production," "(NON-EMPLOYMENT)" (weakness/upskilling signals)
- Any specific year-count number in headlines/summaries
- "Program & Product Leadership" as lead bullet (PM framing)
- "hands-on lab" (close cousin of hands-on)

### Required signal (must always appear):
> "I read, write, and review code throughout the build (now AI-augmented)."
— asserts code competence WITHOUT inviting a coding test.

### Preferred vocabulary:
- Title: **"Healthcare AI Solutions Architect & Technical Leader"**
- Seniority: **"Long career in healthcare IT"**
- AI work: **"AI-native, plan-mode-first workflows"** / "AI-augmented"
- Leadership: "techno-functional leader," "lead through judgment, domain depth, and figure-it-out ability"

### Tone rule:
Matter-of-fact, understated. No: "rare," "unique," "deep expertise," "passionate," "rockstar," "world-class," "expert."
Prefer plain verbs (worked on, led, built, focused on). Let named products / team scale / shipped repos do the bragging.

---

## LOCKED shared headline (identical on Resume / LinkedIn / GitHub / Naukri)

```
Healthcare AI Solutions Architect & Technical Leader · Long career in Healthcare IT · Building Agentic Clinical AI on FHIR · openEHR · MCP
```

## LOCKED shared opening paragraph

Solutions architect and techno-functional leader with a **long career in healthcare IT** — leading product development on **Sunrise Clinical Manager, Sunrise Surgery, and adjacent products** at Altera Digital Health (formerly Allscripts), with teams of **30+ engineers across multiple geographies**. Since **March 2025**, working **full-time and independently** at the intersection of healthcare standards and applied AI — focused on **FHIR (with emphasis on the payer side), openEHR, MCP, agentic LLM workflows, and Radiology AI for early-stage detection of lung disease and breast cancer** — building open-source reference implementations, all published on GitHub.

Day to day I work on architecture, specifications, and getting systems into a working state, using **AI-native, plan-mode-first workflows**. **I read, write, and review code throughout the build (now AI-augmented).** My approach leans on judgment, domain context, and the ability to figure things out — rather than claiming mastery of every framework.

## LOCKED "looking for" line

> *Open to Healthcare AI Solutions Architect, Technical Leader, or Fractional / Advisory roles where deep healthcare-IT domain expertise meets applied AI.*

## LOCKED NDA framing

> "fractional engineering leadership on a Radiology AI venture focused on early-stage detection of lung disease and breast cancer (under NDA)"

---

## Phase 4 — Flagship #1: Agentic Prior-Auth Co-pilot ← START HERE

**GitHub repo**: `prior-auth-copilot` → github.com/pcmedsinge/prior-auth-copilot (create this)
**Local folder**: this workspace — `E:\PracticeApps\AIRelated\PriorAuthCopilot`
**License**: Apache-2.0
**Roadmap surface**: GitHub Projects (public board)

### What it is

Open-source, agentic, FHIR-native Prior Authorization co-pilot targeting the **CMS-0057 Jan 2027** mandate:

- (a) Auto-assembles clinical evidence package from EHR data
- (b) Reasons over payer-specific medical necessity criteria
- (c) Drafts the PA request via Da Vinci PAS / CRD / DTR FHIR profiles
- (d) Explains the decision with citations to payer policy

### Why this project (the regulatory tailwind)

The CMS Interoperability and Prior Authorization Final Rule (CMS-0057-F) creates a **hard Jan 2027 deadline** — every US payer must expose electronic PA APIs. Every payer and provider is scrambling. Open-source PA tooling barely exists. This is the single best-aligned "right project at the right time" for Parag's skill stack in 2026.

### Architecture

```
Intake Agent
    → Evidence Gatherer (FHIR MCP tools from fhir-mcp-suite)
    → Medical Necessity Reasoner (RAG over payer policies — CMS NCDs/LCDs)
    → PAS Bundle Builder (Da Vinci PAS / CRD / DTR FHIR profiles)
    → Reviewer Agent (human-in-loop)
    → Submission
```

- **LangGraph multi-agent** orchestration
- Tools via existing `fhir-mcp-suite` (reuse — strengthens that repo's stars too)
- RAG corpus: CMS NCDs/LCDs + public payer medical policies
- Synthetic patients: **Synthea** — MRI lumbar spine, GLP-1 for obesity, advanced imaging scenarios
- Evals harness from day 1 (links to Flagship #2 clinical-llm-quality-harness)

### Existing repos to reuse (do NOT rebuild):

| Repo | Reuse for |
|---|---|
| `fhir-mcp-suite` | Evidence gathering MCP tools |
| `FHIRPayerProvider_RCM_Knowledge` | Policy knowledge base |
| `fhir-mapping-agent` | FHIR resource construction patterns |
| `bodhi_app` | Knowledge graph patterns for policy KG |
| `cds-hooks-langgraph-agent` | LangGraph patterns |

### Build phases (ship one slice per week to LinkedIn)

#### Phase 4.1 — Week 2 (START HERE)
- [ ] Create GitHub repo `prior-auth-copilot` (Apache-2.0, public)
- [ ] Write landing README: problem framing + architecture (Mermaid diagram)
- [ ] Create `LEADERSHIP.md`
- [ ] Create `docs/adr/` folder with ADR-0001 (why LangGraph over CrewAI/AutoGen)
- [ ] Set up GitHub Projects public board with Week 2–6 milestones
- [ ] Record 2-min Loom: explain the *problem* (not the code) — CMS-0057, what PA is, why it's broken today
- [ ] **LinkedIn post BEFORE any code** — "Here's the problem I'm solving and why it matters in 2026"

#### Phase 4.2 — Week 3
- [ ] Synthea synthetic patient pipeline
- [ ] FHIR MCP integration for evidence retrieval
- [ ] Demo: "Give me all clinical evidence for patient X for an MRI lumbar PA"
- [ ] LinkedIn post: "Shipped: evidence retrieval slice"

#### Phase 4.3 — Week 4
- [ ] Medical necessity reasoning agent
- [ ] RAG over CMS NCD/LCD corpus
- [ ] Demo + LinkedIn post
- [ ] Start Flagship #2 in parallel (see Phase 5)

#### Phase 4.4 — Week 5
- [ ] Da Vinci PAS bundle generation
- [ ] Reviewer agent (human-in-loop)
- [ ] End-to-end demo

#### Phase 4.5 — Week 6
- [ ] Evals + outcome metrics published
- [ ] v1.0 release + release notes
- [ ] Long-form LinkedIn write-up
- [ ] Ask network for feedback / contributors

### What makes this a *techno-functional leader* artifact (not just IC code)

- **`docs/adr/`** — Architecture Decision Records (ADR-0001 onwards). Public, shows lead-level judgment over time.
- **GitHub Projects board** — public, sprints + milestones. Shows delivery discipline.
- **`LEADERSHIP.md`** — "If I led a 4-person squad shipping this for a payer client: staffing plan, hiring bar, eval gate before each release, on-call/runbook approach." Almost no open-source repo has this.
- **User-persona doc** — utilization management nurse, ordering provider, payer reviewer.
- **Loom demos** in the voice of a *tech lead walking stakeholders through a decision*, not a solo dev.
- **Published evals + "what I'd prioritise next quarter and why"** — the exact thinking an EM/Staff engineer does.

---

## Phase 5 — Flagship #2: Clinical LLM Quality Harness (parallel, Weeks 4–6)

**Repo name**: `clinical-llm-quality-harness`
**Why**: Evals = the discipline that distinguishes engineering *leaders* from coders in AI. Low resource cost, high leadership signal.

Three tracks:
1. **Ambient-scribe note quality** — hallucination, omission, SOAP adherence, FHIR write-back correctness (DocumentReference / Encounter / Composition). Shows ambient-scribe domain awareness without competing with Abridge/Nuance DAX/Suki.
2. **Prior-auth reasoning quality** — feeds Flagship #1; tool-call accuracy, citation grounding, decision correctness vs payer policy.
3. **Clinical Q&A grounding** — RAG-on-guidelines accuracy, hallucination rate, citation precision/recall.

---

## Phase 3 — README polish for top 6 pinned repos (can run in parallel)

Apply this template to each repo:
1. Hero block (problem, GIF/demo, outcome metric, badges)
2. "Why this matters" (4–6 lines, product/clinical framing)
3. Architecture diagram (Mermaid)
4. **"Leadership lens"** — "If I led a 3–4 person team building this..."
5. Demo — 60–90 sec Loom in tech-lead voice
6. What's measured (evals, latency, cost, hallucination rate)
7. Quick start (one command)
8. Roadmap + status badge

Priority order: Prior-Auth flagship → `fhir-mcp-suite` → `fhir-mapping-agent` → `bodhi_app` → `openEHR_TrialSafety_TrialMatch` → `fhir-dqm-engine`

---

## Phase 6 — LinkedIn content rhythm (continuous)

- **Monday** — "Shipped:" release notes, demo GIF, repo link (IC voice)
- **Thursday** — "How I'd lead a team to ship this:" sprint plan, staffing, risks, eval gates (leader voice)
- Once per phase: long-form post (1000+ words) on the engineering problem
- Reshare in HL7, FHIR, openEHR, MCP, LangGraph communities

---

## Pinned repo target order (update in GitHub settings when Prior-Auth repo goes live)

1. `prior-auth-copilot` ← pin this first
2. `fhir-mcp-suite`
3. `fhir-mapping-agent`
4. `bodhi_app`
5. `openEHR_TrialSafety_TrialMatch`
6. `fhir-dqm-engine`

---

## Verification / success metrics

Check at **Week 4** and **Week 8**:

1. Recruiter-scan test: 3 people, 30 sec, target answer = "Engineering Manager / Staff Engineer / Tech Lead — Healthcare AI"
2. Pinned repos: 4 of 6 read as agentic/AI-first within 5 seconds
3. Zero typos in repo names, descriptions, topics, READMEs
4. Zero empty repos visible on first page of repositories tab
5. Each pinned repo: hero GIF, Mermaid diagram, demo link, metrics
6. Flagship #1: v0.3+ released, ≥3 LinkedIn posts referenced it, ≥25 stars (stretch)
7. Inbound signal: track DMs/InMails from healthcare-AI hiring managers — Week 8 vs Week 0

---

## Phase 2 — completed actions (for reference)

- Renamed: `pnumoniaApp-Monai` → `pneumonia-monai`
- Renamed: `fhir-mapping--agent` → `fhir-mapping-agent`
- Renamed: `SmartBackEndAppWithHooks-4-3-Langraph` → `cds-hooks-langgraph-agent`
- Renamed: `FHIRMedblock-SmartHealthAI` → `smart-health-ai-companion`
- Topic fixes (3 repos): langraph→langgraph, healtcare→healthcare, geneative-ai→generative-ai
- Archived (12 repos): LaundryWala, 2WheelerTaxi, MCP, EHRApp, FHIR-PatientManagmentApp, MDFHIR-EpicSmartPatientApp-2, FHIR-CernerPractionerApp-3, EpicSmartBackendApp-4-2-Claude, GenAIApp, claudeCodeFeatures, RLHF, openEHR-VitalsBridge-1
- Still pending from Phase 2: learning-lab org (pcmedsinge-lab), SMART app series consolidation into `clinical-smart-on-fhir-reference`, repo descriptions for all kept repos

---

## How to continue in a new Copilot chat session

Paste this prompt to get full context instantly:

> "Starting Phase 4 of the healthcare AI repositioning plan. Read PLAN.md in this workspace first — it has the full context. I need to scaffold the Prior-Auth Co-pilot — Phase 4.1: create the GitHub repo `prior-auth-copilot`, landing README with problem framing and Mermaid architecture diagram, LEADERSHIP.md, ADRs folder, and GitHub Projects board. Use plan mode with Opus for the architecture design."
