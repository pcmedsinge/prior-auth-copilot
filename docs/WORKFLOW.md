# Workflow — how this project is run

This is the operating manual for the Prior-Auth Co-pilot. It captures the working discipline, the document hierarchy, the sub-phase loop, and the GitHub mechanics. Read this once; refer back when starting a new sub-phase or onboarding a collaborator.

---

## 1. Plan-mode principle

**Write the plan first. Get agreement. Then execute.** Never edit files or write code without a written, agreed plan.

- The plan lives in a document — usually a phase doc in [`docs/phases/`](phases/) or an ADR in [`docs/adr/`](adr/).
- "Agreement" means: a human (you) has read the plan and said go. Even if working solo, the act of writing forces clarity.
- When using an AI coding assistant, the rhythm is: **assistant proposes plan → human approves → assistant executes → human reviews diff → commit**. Approval is per-step, not blanket.

Why this matters: agentic systems regress silently. Code-first work without a plan produces demos that look good and break in subtle ways. Plan-first work produces artifacts where every decision is traceable.

---

## 2. Document hierarchy

Each doc has one job. Don't overlap them.

| Document | Purpose | When to edit |
|---|---|---|
| [`README.md`](../README.md) | What this project is + why now + how to find your way around. Landing page. | When status / roadmap / architecture changes materially. |
| [`LEADERSHIP.md`](../LEADERSHIP.md) | How this would be run as a real engagement — squad, hiring bar, eval gates, runbook, risks. | When the leadership story evolves (rare). |
| [`docs/adr/NNNN-*.md`](adr/) | One architectural decision per file. Immutable once Accepted; only status header updates after that. | When a non-trivial choice is made (see ADR-writing rules in [`docs/adr/README.md`](adr/README.md)). |
| [`docs/personas/*.md`](personas/) | Who we build for. Drives feature prioritization. | When persona understanding deepens (e.g., after talking to a real UM nurse). |
| [`docs/phases/4.x-*.md`](phases/) | The plan for one sub-phase — deliverables, ADRs needed, eval gates, Definition of Done. | Live document until the sub-phase starts; frozen once it does. |
| `docs/evals/4.x-scorecard.md` (Phase 4.2+) | Quantitative result of the sub-phase. | Generated at end of each sub-phase. |
| `docs/runbook/` (Phase 4.5) | On-call escalation, common failure modes. | When a new failure mode is discovered. |

**Rule**: if you're about to add a section to a doc and it doesn't fit the table above, that's a signal you need a new doc — not a bigger existing one.

---

## 3. The sub-phase loop

Every Phase 4.x sub-phase follows the same six steps:

```
1. Refine the phase doc   →  docs/phases/4.x-*.md is current and signed off
2. Create the milestone   →  GitHub Issues → Milestones → New
3. Generate the issues    →  one issue per deliverable, attached to milestone + project
4. Work the issues        →  commits reference issue numbers (#7, #8...)
5. Run the eval gate      →  docs/evals/4.x-scorecard.md committed
6. Close the milestone    →  all issues closed + Definition of Done met
                          →  README roadmap row updated
                          →  next sub-phase doc reviewed/refined
```

Step 3 is generated **just-in-time** — only the next sub-phase's issues, never 4 phases ahead. Phase docs evolve as we learn from earlier phases; generating issues too early creates stale work.

---

## 4. ADR cadence

ADRs are written when a choice locks the system into a vendor, standard, or paradigm for more than a quarter, or when a future reader would reasonably ask "why did we do it this way?".

Full when-to-write and lifecycle rules: [`docs/adr/README.md`](adr/README.md).

**Heuristic**: if you're about to type "let's just use X" and X is non-trivial — stop and write the ADR first. Even a 20-line ADR is enough.

---

## 5. Eval gates (Phase 4.2 onward)

Every sub-phase from 4.2 onward ends with a scorecard. The scorecard is a markdown file at `docs/evals/4.x-scorecard.md` with at minimum:

| Metric | Target | Actual | Pass/Fail |
|---|---|---|---|
| Tool-call accuracy | ≥ 0.90 | … | … |
| Citation grounding | 1.00 | … | … |
| End-to-end latency P50 | < 8s | … | … |
| Cost per run | < $X | … | … |

**The release rule**: no scorecard regression vs the previous sub-phase without a corresponding ADR explaining the tradeoff. This is the single most important rule on the project.

---

## 6. Model usage policy (when working with AI assistants)

Different work warrants different model strength. Use the strongest model where the *quality of thinking* matters; use cheaper/faster models for mechanical work.

| Task | Recommended model class |
|---|---|
| ADRs, architecture, phase-doc design, eval-gate design, "should we do X or Y?" conversations | Strongest available (Opus / GPT-5 / equivalent frontier model) |
| Converting a checklist into GitHub Issue bodies; scaffolding boilerplate; routine code edits where the design is already decided | Mid-tier (Sonnet / GPT-4-class) |
| Commit message cleanups, lint fixes, doc formatting | Whatever's cheapest/fastest |

**Plan-mode discipline is enforced by the human, not the model.** Any capable model can follow plan-mode if you keep the "ask before doing" rule. Don't conflate model choice with workflow.

---

## 7. GitHub mechanics — Issues, Milestones, Projects

Three primitives. Same data, three lenses.

### Issues
One Issue = one piece of work. Title + description + status (Open/Closed) + optional labels + optional assignee.

For this repo, Issue ≈ one deliverable from a phase doc. Commits reference Issues by number:

```
git commit -m "feat: synthea loader for MRI lumbar spine module (#7)"
```

This gives instant traceability from code line → why it exists.

### Milestones
A bucket of Issues with a target date. We use **one Milestone per sub-phase**: `Phase 4.2`, `Phase 4.3`, `Phase 4.4`, `Phase 4.5`. Closing all Issues in a milestone gives a 100% progress bar — no spreadsheet needed.

### Projects (board view)
A Kanban/Trello-style board: `Backlog → In Progress → Done`. Same Issues as above, just visualized.

### How they connect
- **Issues** are the data.
- **Milestones** group them by deadline.
- **Projects** visualize them.

You can use any one without the others, but the three together give the cleanest delivery picture.

### Setup checklist (one-time, per repo)

1. **Milestones** (https://github.com/pcmedsinge/prior-auth-copilot/milestones → New milestone)
   Create four: `Phase 4.2 — Evidence retrieval`, `Phase 4.3 — Reasoner`, `Phase 4.4 — PAS Bundle + Reviewer`, `Phase 4.5 — Evals + v1.0`. Each with a target date.

2. **Project board** (https://github.com/pcmedsinge?tab=projects → New project → Board template)
   Name: `Prior-Auth Co-pilot Roadmap`. Link this repo. Make Public if you want it visible.

3. **Generate Issues per sub-phase** — see section 8.

### Per-issue workflow

1. Open Issues → **New issue**
2. Paste title + body (generated per section 8)
3. Right sidebar:
   - **Milestone**: pick the relevant `Phase 4.x`
   - **Projects**: pick `Prior-Auth Co-pilot Roadmap`
   - **Labels** (optional): `type:adr`, `type:code`, `type:eval`, `type:docs`
4. **Submit**
5. Work it; commits reference the issue number; close when done (commit message with `Closes #7` auto-closes on merge).

---

## 8. Generating Issues from a phase doc

When a sub-phase starts:

1. Open the phase doc (e.g., `docs/phases/4.2-evidence-retrieval.md`).
2. Each top-level deliverable in the "Scope" section becomes one Issue.
3. ADRs likely needed → one Issue each, labelled `type:adr`.
4. The eval scorecard → one Issue, labelled `type:eval`.
5. The demo target → one Issue, labelled `type:code`.

The AI assistant generates the Issue text (title + body) as a single markdown file you paste from. Format per Issue:

```
### Issue: <title>

**Milestone**: Phase 4.x
**Labels**: type:<kind>

<body — context, scope, acceptance criteria, links to relevant phase doc section>
```

You paste, click submit, repeat. ~5–8 Issues per sub-phase, ~10 minutes.

---

## 9. Commit message convention

Conventional Commits, lightweight:

```
feat:     new capability
fix:      bug fix
docs:     doc-only change
chore:    repo plumbing (deps, ignores, configs)
refactor: code restructure, no behavior change
test:     test/eval changes
adr:      ADR added or updated
```

Reference Issues with `(#N)`; close with `Closes #N` in the commit body.

---

## 10. Branching

- **Solo phase**: commit straight to `main` is fine. The discipline is the plan doc, not the branch.
- **When collaborators land** (Phase 4.5+): one branch per Issue, PR back to `main`, eval gate must pass before merge.

---

## 11. What this workflow deliberately is *not*

- It is not Jira. No story points, no velocity, no burndown.
- It is not Scrum. Sub-phases are time-boxed, but there are no daily standups (solo project).
- It is not "ship fast, document later". The docs *are* the spec.

The goal is the minimum process that keeps the project legible, auditable, and shippable — and no more.

---

*This file evolves. If something here is wrong or unclear in practice, update it.*
