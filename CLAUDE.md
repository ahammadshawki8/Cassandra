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

- **Live audit dashboard.** The workbook rendered as a grid with findings highlighted in place.
- **Blast radius overlay.** Downstream cells illuminate as impact propagates through the DAG. This is the single clearest visual explanation of why a finding matters.
- **Agent trace stream.** The live reasoning chain, including rejected patches and the reason for rejection.
- **Before and after diff.** The headline figure, previous value against corrected value.

---

## Architecture

### Design principles

1. **Deterministic before probabilistic.** Never spend a model call on something a parser can do exactly. The LLM is reserved for judgement that genuinely requires language understanding.
2. **Nothing is asserted that is not verified.** Every claim reaching the user passed a recalculation check first.
3. **Least privilege between agents.** Hunters hold read only graph access. Only the Patcher may propose a mutation. Only the Verifier may execute a recalculation. Enforced in code, not convention.
4. **Every stage is resumable.** State lives in Firestore, not in memory. A worker can die mid run and the run continues.

### User flow

Strictly linear. There are no orphan features and nothing the user must discover.

```
1. Drop workbook into bucket
        |
2. Cassandra wakes automatically (no user action)
        |
3. Watch findings appear, ranked by materiality
        |
4. Click a finding, see its blast radius on the grid
        |
5. See the proposed patch and its verification verdict
        |
6. Accept or dismiss
        |
7. Drop the next version. Cassandra diffs it against this one.
```

The user takes exactly one deliberate action to start: dropping a file. Everything before step 6 is autonomous.

### System diagram

```
   workbook.xlsx
        |
        v
  [ Cloud Storage ]  --object.finalize-->  [ Pub/Sub ]
                                                |
                                                v
                                     [ Cloud Run  scale to zero ]
                                                |
                                    +-----------+-----------+
                                    |                       |
                                    v                       v
                        [ CARTOGRAPHER ]            [ Firestore ]
                        deterministic, no LLM        run state
                        parse / DAG / cluster        findings
                        R1C1 signatures              patch attempts
                                    |                dismissals
                                    v                lineage
                    +---------------+---------------+
                    |    HUNTING FLEET  (parallel)  |
                    |    read only graph access     |
                    |                               |
                    |  Hardcode      Range          |
                    |  Pattern       Sign           |
                    |  Reference     Semantic       |
                    +---------------+---------------+
                                    |
                                    v
                          [ ADJUDICATOR ]
                     rank by blast radius x impact
                                    |
                                    v
                            [ PATCHER ]
                       proposes concrete cell edit
                                    |
                                    v
                            [ VERIFIER ] <--------+
                       recalculate the workbook   |
                                    |             |
                          +---------+---------+   |
                          |                   |   |
                       REJECT               PASS  |
                    with reason ---------------->-+
                    (bounded retries,          |
                     then quarantine)          v
                                        [ Dashboard ]
                                     grid / blast radius
                                     trace / value diff

   Cross cutting:  OpenTelemetry -> Cloud Trace   (full reasoning chain)
                   Gemini 3.5 Flash via Vertex AI (all agent reasoning)
                   Google ADK                     (fleet orchestration)
```

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
- [ ] Create GCP project, enable billing, enable APIs (Vertex AI, Cloud Run, Storage, Pub/Sub, Firestore, Cloud Trace)
- [ ] Create the ingestion bucket and Pub/Sub topic with the object finalize notification
- [ ] Deploy a stub Cloud Run service and prove the end to end pipe with a dummy file
- [ ] Author the demo workbook: a realistic multi sheet financial model with planted defects, one of which is designed so the first patch attempt fails verification
- [x] Repository scaffold, `.gitignore`, dependency manifest

### Phase 1 — Deterministic core

- [x] Workbook parser producing a cell level model
- [x] Formula dependency DAG construction
- [x] Region clustering and R1C1 signature normalization
- [x] Blast radius computation over the DAG
- [x] Recalculation harness wrapping the calculation oracle
- [x] Unit tests against the demo workbook with known defect locations

### Phase 2 — Agent fleet

- [ ] ADK agent scaffold with Vertex AI and Gemini 3.5 Flash wired
- [ ] Tool layer with per agent scoping enforced
- [ ] Six hunter agents
- [ ] Adjudicator with materiality ranking
- [ ] Patcher producing structured cell edits
- [ ] Verifier with recalculation, predicted versus actual assertion, and rejection reasons
- [ ] Bounded retry and quarantine handling
- [ ] Firestore persistence for runs, findings, attempts, verdicts
- [ ] OpenTelemetry instrumentation to Cloud Trace
- [ ] Idempotency on Pub/Sub message ID

### Phase 3 — Operator surface

- [ ] Live dashboard shell
- [ ] Workbook grid renderer with in place finding highlights
- [ ] Blast radius overlay animation
- [ ] Agent trace stream including rejections
- [ ] Before and after value diff
- [ ] Materiality ranked finding list with accept and dismiss

### Phase 4 — Regression sentinel and hardening

- [ ] Version diff between workbook revisions
- [ ] Root cause attribution from moved output back to originating edit
- [ ] Dismissal memory across runs
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

**Status:** Phase 0 in progress.

**Done**
- Project direction locked: continuous regression sentinel with closed loop verified repair
- Competitive and academic landscape researched, differentiation established
- Public repository created at `github.com/ahammadshawki8/Cassandra`
- Python 3.11 venv established at `.venv` (system default is 3.14, too new for the scientific stack)
- **Calculation oracle de risked.** `formulas` 1.3.4 installs and imports cleanly on 3.11. This was the single largest technical risk and it is now retired.
- `google-adk` 2.8.0 and `google-genai` 2.20.0 installed and importing
- `opentelemetry-sdk` 1.42.1 arrives as an ADK dependency, so the observability layer needs no extra install
- This file, committed and pushed

- Google Cloud CLI 582.0.0 installed at `C:\Users\Shawki\google-cloud-sdk`, bundled python build, no admin rights. Note for anyone reproducing this: the documented rapid channel URL returns 404, the working path is `/rapid/downloads/`.
- **Phase 1 deterministic core complete.** `model`, `refs`, `parser`, `graph`, `oracle`.
- **The verifier is proven end to end.** It accepts a correct patch and rejects all four failure modes: a hallucinated prediction, a no op patch, a patch producing an Excel error, and any patch causing collateral movement outside the target's blast radius. The source workbook is never mutated.
- 30 tests passing via `pytest`

**In progress**
- Phase 2, the agent fleet

**Blocked / needs the user**
- `gcloud auth login` must be run by the user, it requires a browser
- GCP project ID and confirmation that billing is enabled

**Verified environment**

| Component | Version |
| --- | --- |
| Python (project venv) | 3.11 |
| `formulas` | 1.3.4 |
| `google-adk` | 2.8.0 |
| `google-genai` | 2.20.0 |
| `opentelemetry-sdk` | 1.42.1 |
| `networkx` | 3.6.1 |
| `openpyxl` | 3.1.5 |
| GitHub account | `ahammadshawki8` |

**Open risks**
- `formulas` may not evaluate every Excel function. Mitigation: the demo workbook is authored by us, so it uses only well supported functions. Unevaluable formulas degrade to "unverified" rather than failing.
- Cloud Run cold start during recording. Mitigation: min instances 1 while filming, 0 afterwards.
- Gemini Enterprise Agent Platform services (Agent Registry, Memory Bank) are new with thin documentation. They are a stretch goal and must never be on the critical path.

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
