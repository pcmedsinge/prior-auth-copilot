# Leadership lens — how I'd lead a squad shipping this

Notes on how this project would be run as a real engagement: squad shape, hiring bar, sprint cadence, eval gates, risk register, and on-call/runbook approach. Written as if a payer or provider client asked me to take this from reference implementation to a 6-month pilot in production.

---

## 1. Squad shape (4 people, ~6 months to pilot)

| Role | Headcount | Why this shape |
|---|---|---|
| **Tech lead / solutions architect** | 1 (me) | Owns architecture, ADRs, payer-side integration design, eval framework, stakeholder narrative. Reads/writes/reviews code (AI-augmented) but does not own a feature backlog. |
| **Senior FHIR / integrations engineer** | 1 | Owns Da Vinci PAS / CRD / DTR Bundle construction, payer FHIR endpoint integration, Synthea pipeline, conformance testing against the [Inferno PAS test kit](https://github.com/onc-healthit/onc-certification-g10-test-kit). |
| **Applied AI / agents engineer** | 1 | Owns LangGraph graph, agent prompts, tool-calling correctness, RAG quality over the policy corpus, MCP server wiring. |
| **Clinical informaticist (fractional, 0.5 FTE)** | 0.5 | Owns medical necessity rubric, policy-to-rules translation, golden eval set creation. Reports into the tech lead, not into product, because the eval set IS the spec. |

**Not on this squad** (deliberately): a full-time PM. At this stage the ADRs + persona docs + eval harness *are* the product spec. A PM is added at month 5 when we have a paying pilot customer.

---

## 2. Hiring bar (what I'd look for, in order)

For the FHIR engineer:
1. Has shipped at least one **Da Vinci IG**-based feature end-to-end (PAS / CRD / DTR / PDex / Plan-Net). Asks unprompted about US Core profile versions.
2. Knows the difference between `Claim` and `ClaimResponse` in PAS and *why* PAS reuses the financial Claim resource for a clinical workflow. (Cultural-fit screen: if they think this is weird, good — they have judgment. If they think it's elegant, also good — they've read the IG.)
3. Comfortable reading a payer's medical policy PDF and pointing at the 3 sentences that become structured rules.

For the agents engineer:
1. Has built a **multi-step agent that calls real tools** (not a chat demo). Can describe one concrete failure mode of tool-calling and how they mitigated it.
2. Treats **evals as a first-class artifact**, not as an afterthought. Has opinions on golden sets vs LLM-as-judge and when each is appropriate.
3. Knows when *not* to use an LLM. (The PAS Bundle assembly is deterministic; only reasoning is LLM-mediated.)

**Red flag, every role**: candidates who lead with framework names ("I'm a LangChain expert"). Frameworks change every 6 months; judgment doesn't.

---

## 3. Sprint cadence and eval gates

Two-week sprints. Each sprint must end with:

1. A runnable end-to-end demo (no slideware).
2. **Eval scorecard** posted to the public Projects board:
   - Tool-call accuracy on the golden set
   - Citation grounding rate (fraction of reasoning steps with a verifiable policy citation)
   - PAS Bundle conformance pass rate (Inferno / `$validate` against `us-core` and `davinci-pas` profiles)
   - End-to-end latency P50 / P95
   - Cost per PA draft ($)
3. One ADR added or updated if any non-trivial architectural choice was made.
4. One LinkedIn post (alternating IC-voice and leader-voice — see Phase 6 of the overall plan).

**The release gate, every sprint**: no scorecard regression vs the previous sprint without a corresponding ADR explaining the tradeoff. This is the single most important rule on the team. AI-system quality regresses silently; the gate is what keeps it honest.

---

## 4. Risk register (what would kill this project)

| Risk | Mitigation |
|---|---|
| Payer-policy corpus is too messy to RAG over reliably | Start with CMS NCDs (clean, structured). Layer in Aetna / UHC / Humana public LCDs only after the NCD pipeline scores >0.9 on citation grounding. Treat each payer as a separate corpus with its own eval set. |
| LLM hallucinates medical necessity justifications | Decision-making is **never** the LLM's. The LLM proposes a draft + citations; a deterministic checker verifies every cited paragraph exists in the corpus; the UM nurse approves. The LLM is a drafter, not a decider. |
| Da Vinci PAS IG changes before Jan 2027 | Pin the IG version in an ADR; track the HL7 ballot calendar; allocate one sprint per quarter for IG-version uplift. |
| Synthetic data doesn't reflect real-world payer edge cases | Pair every Synthea scenario with one anonymized real-world case (from a design-partner provider) before claiming "production-ready". |
| Vendor lock-in to a single model | Abstract the model behind an interface from day one; run the eval harness against at least two model families (e.g., GPT-4 class + Claude class + an open-weights option like Llama 3.1 70B or MedGemma). |

---

## 5. On-call & runbook approach

Even in pilot, this system writes to a payer-facing API. That makes it production from day one in the eyes of compliance.

- **On-call rotation**: tech lead + FHIR engineer share a 1-week rotation. Agents engineer is *not* on call — they own the model layer, not the integration layer.
- **Runbook lives in the repo** at `docs/runbook/` (added in Phase 4.5). Every alert must link to a runbook entry; no orphan alerts.
- **SLOs (pilot)**: 99.0% of PA drafts complete in <60s; citation grounding ≥0.95 on the golden set; zero PAS Bundles submitted that fail `$validate`.
- **Audit trail**: every agent decision, every tool call, every model output is logged with patient and request IDs. PHI-aware logging from day one.

---

## 6. Stakeholder narrative (how I'd brief the executive sponsor monthly)

One slide. Three numbers:
1. **Drafts produced this month** (volume).
2. **UM-nurse acceptance rate** (the only quality metric that matters at pilot stage).
3. **Average minutes saved per PA vs the baseline workflow** (the only ROI metric that matters).

Everything else — eval scores, latency percentiles, cost per draft — is on the engineering dashboard, available on demand, not in the exec brief.

---

## 7. What I will not do

- Build a custom LLM. Wrong problem, wrong leverage.
- Build a payer-side adjudication engine. That is the payer's job; we draft *to* their criteria, not replace them.
- Optimize for stars before the eval harness exists. Demos without evals are theater.
- Hide the failure modes in the demo videos. The Loom walkthroughs will show the agent getting things wrong, and how the human-in-the-loop catches it.

---

*Last updated: Phase 4.1 · scaffolding. Will evolve with each ADR.*
