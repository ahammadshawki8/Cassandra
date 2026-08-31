# CASSANDRA

> Persistent project memory. This file is the single source of truth. Update it in place as work progresses rather than creating new documents.

---

## Elevator Pitch

*(184 characters)*

> Cassandra is continuous integration for the spreadsheets that run your company. An autonomous agent fleet finds the defect, writes the fix, and proves it by recalculating the workbook.

---

## Description

Cassandra is an event driven fleet of AI agents that treats business critical spreadsheets the way modern engineering treats source code: as something that must be continuously tested, diffed against its previous version, and never silently broken.

Drop a workbook into a Cloud Storage bucket. Cassandra wakes from zero, parses the file into a formula dependency graph, dispatches a fleet of specialist agents to hunt distinct classes of defect, ranks what it finds by real financial materiality, writes a concrete patch, and then verifies that patch by recalculating the entire workbook. If the recalculation does not move the target cell exactly as predicted, or moves any other cell it should not have, the patch is rejected and sent back for revision.

Nothing is reported to the user that the system has not first proven to itself.

Drop the next version of the same workbook and Cassandra becomes a regression sentinel: it diffs v12 against v11, identifies which edit broke which downstream number, and remembers every finding a human already dismissed so it never nags twice.

---

## The Problem

Spreadsheets are the largest untested codebase on earth. They allocate budgets, price deals, and set national policy, and essentially none of them are under test.

The research is unambiguous:

- **94%** of spreadsheets contain at least one error (meta analysis across seven studies)
- **95%** of financial models audited by KPMG contained major errors; 75% contained significant accounting errors
- **~5%** contain outright "show stopper" errors, per interviews with professional spreadsheet auditing principals
- Developers estimate their own error rate at **10 to 18%**. The measured rate is **86%**.

That final gap is the actual problem. The errors are everywhere, they are catastrophic, and the people who wrote them are confident they are not there. A wrong formula looks exactly like a right one.

The consequences are historical record. The Reinhart and Rogoff austerity paper shaped global fiscal policy off a summation range that omitted five rows. JPMorgan's London Whale loss involved a spreadsheet copy and paste error inside a $6.5B hole.

**The friction Cassandra removes:** nobody audits spreadsheets, because auditing them by hand is unbearable and the existing tools require a human to stop, open a file, and read a wall of warnings. So it never happens, and the error ships.

---

## Features

### Core pipeline

- **Zero touch ingestion.** A workbook landing in a Cloud Storage bucket emits an event. No UI, no upload button, no OAuth consent screen. The agent wakes on its own.
- **Deterministic cartography.** The workbook is parsed into a formula dependency DAG, contiguous regions are clustered, and each region gets an R1C1 normalized signature. This stage is pure code with no model calls, because a parser does this better than an LLM.
- **Specialist hunting fleet.** Six agents with strictly scoped read only tools, running in parallel, each responsible for one defect class.
- **Materiality adjudication.** Findings are ranked by blast radius through the DAG multiplied by the magnitude of impact on identified output cells, so the top finding is the one that actually moves money.
- **Patch synthesis.** A concrete cell level edit, not prose advice.
- **Verification by recalculation.** The patch is applied to a copy and the workbook is recalculated. The verifier asserts the target cell moved as predicted and that no unintended cell moved beyond tolerance. Rejected patches return to the patcher with the specific failure reason. Retries are bounded, then the finding is quarantined.

### The defect hunters

| Agent | Defect class |
| --- | --- |
| Hardcode Hunter | Literal constants buried inside formulas (the London Whale class) |
| Range Auditor | Off by one range boundaries, omitted final rows, headers pulled into sums (the Reinhart and Rogoff class) |
| Pattern Breaker | Cells deviating from their region's R1C1 signature |
| Sign and Polarity | Cashflow and accounting sign inversions |
| Reference Integrity | `#REF!`, dangling cross sheet references, stale external links |
| Semantic Auditor | Reads the human label and checks the formula computes what the label claims |

The Semantic Auditor is the only hunter that fundamentally requires a language model. No static analyzer can determine that the cell labeled "Net Margin" is computing gross.

### Regression sentinel

- **Version diffing.** Given a newer revision of a known workbook, Cassandra identifies which edits occurred and which downstream outputs changed as a result.
- **Root cause attribution.** Traces a moved output number back to the specific originating edit through the dependency graph.
- **Institutional memory.** Findings dismissed by a human are remembered across runs and sessions, so the system never re raises settled matters.
- **Cross workbook lineage.** Tracks when one model feeds another, so a break in an upstream model surfaces against every downstream consumer.

### Operator surface

Strictly linear, and deliberately small. The person looking at this has never seen the tool before.

- **One control.** A single button. Nothing else is on screen at rest.
- **One activity line.** What she is doing right now, in plain words, rather than a log firehose.
- **One headline.** The figure that was wrong, struck through, beside the figure that is right.
- **The fixes.** Formula before and after, the value that moved, and whether it was proven or needs a human.
- **A rejected patch is promoted, not buried.** When a repair fails verification and is retried, the interface says so in words. It is the clearest evidence the loop is real.

Everything else, the full trace included, is collapsed behind one link. Design direction is kawaii in shape and palette, professional in typography: every formula and figure is set in a mono face, because a tool auditing financial models cannot read as a toy.

---

## Architecture

### Design principles

1. **Deterministic before probabilistic.** Never spend a model call on something a parser can do exactly. The LLM is reserved for judgement that genuinely requires language understanding.
2. **Nothing is asserted that is not verified.** Every claim reaching the user passed a recalculation check first.
3. **Least privilege between agents.** Hunters hold read only graph access. Only the Patcher may propose a mutation. Only the Verifier may execute a recalculation. Enforced in code, not convention.
4. **Every stage is resumable.** State lives in Firestore, not in memory. A worker can die mid run and the run continues.

### User flow

One column, three states. Nothing appears until it is relevant, and there are no orphan features.

```
        ( mascot )
        Cassandra
   she checks the spreadsheet your numbers
   come from, and proves every fix

   +----------------------------+
   |  [ Check this workbook ]   |   one button, the only control
   +----------------------------+
                |
   +----------------------------+
   | Writing a fix              |   one line, the current activity
   | ......o                    |
   +----------------------------+
                |
   +----------------------------+
   | Operating Income           |
   | 6,246,545 -> -2,481,455    |   the number that was wrong
   |      off by 8,728,000      |
   +----------------------------+
                |
   five fixes, each proven by recalculation
```

The autonomous path needs no interface at all: a workbook landing in the bucket starts everything. The button exists so the whole thing can be shown without waiting on an upload.

### System diagram

See `docs/architecture.md`, which carries three mermaid diagrams: the whole system, the verification loop as a sequence, and where the model is trusted against where it is not. GitHub renders them inline.

### Stack

| Layer | Technology |
| --- | --- |
| Model | Gemini 3.5 Flash via Vertex AI |
| Agent framework | Google ADK |
| Compute | Cloud Run, scale to zero |
| Eventing | Cloud Storage notifications, Pub/Sub |
| State | Firestore |
| Observability | OpenTelemetry, Cloud Trace |
| Calculation oracle | `formulas` (Python Excel interpreter) |
| Graph | `networkx` |

### Reliability

- **Idempotency.** Keyed on Pub/Sub message ID. A redelivered message must never produce a duplicate run or a duplicate patch.
- **Bounded retries.** The patch and verify loop cannot spin. After N rejections the finding is quarantined and surfaced as unresolved rather than silently dropped.
- **Graceful degradation.** If the calculation oracle cannot evaluate a formula, the finding is reported as unverified and clearly labelled as such. It is never presented as proven.

---

## Research Foundation

This project stands on a decade of peer reviewed literature rather than claiming to be unprecedented.

**Error prevalence**
- Panko, *What We Know About Spreadsheet Errors* and the Dartmouth Tuck critical literature review. Establishes the 94% figure and the 86% versus 10 to 18% perception gap.
- Panko and Halverson, spreadsheet error taxonomy. Source of the defect class breakdown the hunting fleet mirrors.
- KPMG financial model survey. 95% major error rate.

**Detection technique**
- *CUSTODES: Automatic Spreadsheet Cell Clustering and Smell Detection Using Strong and Weak Features* (ICSE 2016). Establishes that smelly cells appear as outliers within clusters of cells sharing a tabulation style, at F measure 0.72. The Cartographer's region clustering and the Pattern Breaker agent implement this insight directly.
- *ExceLint: Automatically Finding Spreadsheet Formula Errors* (arXiv 1901.11100).
- Hermans, Pinzger, van Deursen, on code smells in spreadsheet formulas and inter worksheet smells.

**LLMs applied to spreadsheets**
- *SpreadsheetLLM: Encoding Spreadsheets for Large Language Models* (arXiv 2407.09025), Microsoft. Structural anchor based compression for feeding grids to language models.
- *Benchmark Dataset Generation and Evaluation for Excel Formula Repair with LLMs* (arXiv 2508.11715). Establishes verification of LLM generated formula repairs against a calculation engine as sound methodology.
- *FLARE: Large Language Models for Spreadsheets* (arXiv 2506.17330).

**Agentic repair**
- RepairAgent, autonomous LLM program repair operating on a localize, fix, test, iterate loop. The architectural precedent for Cassandra's patch and verify cycle.

---

## Prior Art and Differentiation

Honesty here is a feature. Judges will search, and arriving at the prior art before they do reads as rigor.

### What already exists

| Prior work | What it does |
| --- | --- |
| PerfectXL (commercial, $249 to $2,000/yr) | Static inspection, pattern highlighting, broken formula sequences, risk reports |
| Operis OAK (commercial) | Excel add in for model structure analysis, standard in large banks |
| Spreadsheet Detective, Excel Risk Check | Static audit tooling |
| CUSTODES, ExceLint (academic) | Automated smell and error detection |
| arXiv 2508.11715 (academic) | LLM formula repair with calculation engine verification |

### The gap every one of them shares

**They audit a static artifact, at a single point in time, only when a human decides to stop and open a file.** They are linters. They require the exact human attention whose absence is the entire cause of the problem.

### What Cassandra does that none of them do

1. **It runs as infrastructure, not as a tool.** Nobody has to remember to invoke it. The audit is triggered by the file existing, which removes the human bottleneck that is the actual root cause.
2. **It catches the regression, not just the defect.** No tool above answers "this model was correct last week, which edit broke it, and which downstream number moved." That is version aware root cause attribution across revisions.
3. **It proves its own fixes.** Existing tools emit warnings for a human to adjudicate. Cassandra writes the patch and refuses to surface it until recalculation confirms it does exactly what was predicted and nothing more.
4. **It ranks by money, not by rule violation.** Static analyzers list every violation equally. Cassandra sorts by blast radius through the dependency graph multiplied by impact on real output cells.
5. **It remembers.** Dismissed findings stay dismissed across sessions and revisions. Institutional memory is what separates a tool people use once from a system people leave running.

The honest summary: the detection layer stands on established research, and that is a strength. The **autonomous, continuous, self verifying, regression aware** composition does not exist as a product or a paper.

---

## Why This Wins

Mapped against the published judging criteria.

### Innovation and Operational Utility (40%)

The friction is quantified, historically catastrophic, and universal. Every judge has been burned by a spreadsheet. The autonomy is genuine: the agent is triggered by a file event, decides what matters, writes a fix, and validates it, with the human entering only at the accept or dismiss step. This is not a chat loop with tools bolted on.

### Architectural Discipline and Tech Stack (30%)

- Clean separation between deterministic parsing and probabilistic judgement, with an explicit rationale rather than reflexive LLM usage
- Strict least privilege tool scoping across agents, enforced in code
- Externalized, resumable state with idempotency on redelivery
- A bounded, failure tolerant self correction loop that directly answers the rubric's question about recovering from a hallucinating worker agent
- Full OpenTelemetry reasoning chain traces

### Demo and Production Readiness (30%)

The demo is unusually strong because the system has a **ground truth oracle**. Most agent demos ask a judge to believe that plausible output is correct. Cassandra recalculates the workbook and shows the number move. The most valuable moment in the video is the verifier **rejecting** a patch and demanding a revision, because that proves the loop is real rather than theatre.

Google Cloud proof is banked in the first sixty seconds: object lands in the bucket, Pub/Sub delivers, Cloud Run scales from zero, all visible in the console before anything else can go wrong.

---

## Implementation Plan

### Phase 0 — Foundation and Google Cloud proof

- [x] Resolve Python toolchain (3.11 venv, verify `formulas` and `google-adk` install)
- [x] Install and authenticate `gcloud` CLI
- [x] Create GCP project, enable billing, enable APIs (Vertex AI, Cloud Run, Storage, Pub/Sub, Firestore, Cloud Trace)
- [x] Create the ingestion bucket and Pub/Sub topic with the object finalize notification
- [ ] Deploy a stub Cloud Run service and prove the end to end pipe with a dummy file
- [x] Author the demo workbook: a realistic multi sheet financial model with planted defects, one of which is designed so the first patch attempt fails verification
- [x] Repository scaffold, `.gitignore`, dependency manifest

### Phase 1 — Deterministic core

- [x] Workbook parser producing a cell level model
- [x] Formula dependency DAG construction
- [x] Region clustering and R1C1 signature normalization
- [x] Blast radius computation over the DAG
- [x] Recalculation harness wrapping the calculation oracle
- [x] Unit tests against the demo workbook with known defect locations

### Phase 2 — Agent fleet

- [x] ADK agent scaffold with Vertex AI and Gemini 3.5 Flash wired
- [x] Tool layer with per agent scoping enforced
- [x] Six hunter agents
- [x] Adjudicator with materiality ranking
- [x] Patcher producing structured cell edits
- [x] Verifier with recalculation, predicted versus actual assertion, and rejection reasons
- [x] Bounded retry and quarantine handling
- [x] Firestore persistence for runs, findings, attempts, verdicts
- [ ] OpenTelemetry instrumentation to Cloud Trace
- [x] Idempotency on Pub/Sub message ID

### Phase 3 — Operator surface

- [x] Live dashboard shell
- [x] Workbook grid renderer with in place finding highlights
- [x] Blast radius overlay animation
- [x] Agent trace stream including rejections
- [x] Before and after value diff
- [x] Materiality ranked finding list with accept and dismiss

### Phase 4 — Regression sentinel and hardening

- [x] Version diff between workbook revisions
- [ ] Root cause attribution from moved output back to originating edit
- [x] Dismissal memory across runs
- [ ] Lightweight agent registry with capability manifests and versions
- [ ] README with spin up instructions and prior art section
- [ ] Architecture diagram asset
- [ ] Deploy, set min instances to 1 for recording

### Phase 5 — Submission

- [ ] Demo video (recorded in parallel by teammate)
- [ ] Devpost write up: features, technologies, data sources, findings and learnings
- [ ] Track selection finalized
- [ ] Social post with `#AllThingsAgenticHackathon`
- [ ] Set min instances back to 0

---

## Current State

**Status:** Phase 3 in progress. Core, agents, and cloud infrastructure all live and working.

### Verified working end to end

- **Vertex AI with `gemini-3.5-flash`.** Note for anyone reproducing this: Gemini 3.x is served only from `location=global` on Vertex. `us-central1` returns 404 for every 3.x model while serving 2.5 happily, which reads as "no access" and is not.
- **Event pipeline proven.** A workbook uploaded to the bucket fires `OBJECT_FINALIZE` and the message arrives on the `cassandra-worker` subscription.
- **Firestore** `(default)`, nam5, native mode.
- **The full audit pipeline**, parse through verified repairs, on the demo workbook in about two minutes.

### What the agents actually did

- The Semantic Auditor caught `PL!C10`, labelled Net Margin while computing gross margin. No deterministic rule can find this.
- The Adjudicator dismissed `Revenue!B5` unprompted and for the right reason: a boundary cell legitimately seeding a series from an assumption.
- The patch loop self corrected on `Revenue!D12`. Attempt one was rejected by recalculation as changing nothing; attempt two recognised the defect as latent and verified by counterfactual.

### Infrastructure

| Resource | Identifier |
| --- | --- |
| Project | `cassandra-507217`, number 987446871604 |
| Bucket | `gs://cassandra-507217-workbooks` |
| Topic | `cassandra-workbook-landed` |
| Subscription | `cassandra-worker` |
| Firestore | `(default)`, nam5, native |
| Model | `gemini-3.5-flash`, Vertex AI, `location=global` |

### Bugs found and fixed during the build

Every one of these was real and would have shipped:

1. **Regex backtracking** split `LOG10(` into column LOG row 1 followed by `0(`. Fixed with a digit lookahead.
2. **Quoted sheet names** lost their quotes in R1C1 rewriting, so `'P L'!A1` became invalid.
3. **Detectors read openpyxl's value cache**, which is empty for any workbook not written by Excel. Two of six planted defects were silently missed. They now read computed values from the oracle.
4. **Phantom collateral rejections.** The calculation engine spells a blank cell differently from openpyxl, so None against empty counted as movement and rejected valid patches.
5. **Blank out patches passed verification.** Pointing a formula at an empty cell satisfies both conditions, the value moved and nothing else did, which made emptying a cell the cheapest way to pass. Now rejected outright.
6. **Invented references.** The Patcher occasionally named a cell just outside the used range. Formulas are now read before they are calculated and rejected on inspection.
7. **Over aggressive upstream suppression.** Treating every finding inside a repaired cell's blast radius as a symptom discarded two genuine independent defects, including the sign inversion. Suppression now requires the finding to be purely semantic: if a structural detector read the cell's own formula and objected, no upstream repair explains it away.

### Known limitations, stated honestly

- Recalculation proves a repair is mechanically sound. It cannot prove the repair expresses what the author meant. Where the workbook no longer holds enough information to infer intent, the clearest case being a reference whose target was deleted, the repair is labelled `needs_human_intent` rather than presented as proven.
- `formulas` does not implement every Excel function. Anything it cannot evaluate degrades to unverified and is never reported as proven.

### Deployed and proven in the cloud

- **Service:** `https://cassandra-gibp4zik7a-uc.a.run.app`
- **`/api/health`** reports `store: firestore`, `model: gemini-3.5-flash`, `vertex: TRUE`
- **The autonomous path works end to end.** A workbook dropped into the bucket fired `OBJECT_FINALIZE`, Pub/Sub pushed to Cloud Run, and the audit ran with no human action: 8 findings, 5 repaired, headline `Operating Income 6,246,545 -> -2,481,455`, persisted to Firestore.

### Two more traps, both cloud specific

8. **Cloud Run reserves `/healthz`.** It is answered by Google's frontend and never reaches the container, so the endpoint returns Google's own 404 page while every other route serves normally. It reads exactly like a service that failed to start. Health lives at `/api/health`.
9. **The Cloud Build service account lacks roles it needs by default.** Without `storage.objectViewer` the build cannot read the source archive it was just handed, which surfaces as a 403 on an object that plainly exists.
10. **numpy scalars broke the detail response.** Values reaching Firestore as numpy floats encode to a different byte length than the default encoder measures when setting Content-Length, so the body overran its own header mid response. Detail payloads are now built and measured in one pass.

### Remaining

- README spin up instructions verified against a clean clone
- Demo video, recorded by teammate
- Devpost submission

---

## Working Rules

**Writing**
- No em dashes or en dashes in any prose. Use commas, colons, or separate sentences.
- No emoji anywhere, including commit messages, code comments, and UI. Where an icon is needed, use an inline SVG.

**Git**
- Author and commit as `ahammadshawki8` only.
- Never add Claude as a co author, contributor, or trailer. No `Co-Authored-By`, no generated by footers, no session links.
- Commit and push after each completed milestone.
- Remote: `github.com/ahammadshawki8/Cassandra`, public.

**Documentation**
- This file is the primary and preferred document. Prefer editing it over creating anything new.
- Do not create summary files, status reports, progress notes, or session recaps.
- Additional markdown files only when genuinely required. `README.md` is required by the hackathon rules and is therefore justified. Almost nothing else is.

**Code**
- Deterministic logic over model calls wherever both are possible.
- No orphan features. If it is not on the linear user flow above, it does not get built.
