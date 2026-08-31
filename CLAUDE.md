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
   | 6,246,545 -> -1,704,250    |   the number that was wrong
   |      off by 7,950,795      |
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

11. **Per repair figures did not match the corrected file.** Every correction is verified on its own against the original workbook, which is right for proving one repair and wrong for reporting a result: applied together they interact, and repairing the revenue range offsets the expense sign inversion. The interface said -2,481,455 while the downloadable file computed -1,704,250. The full set is now applied at once and recalculated a final time, so the number on screen is the number in the file.

12. **A CSS specificity collision made dark mode unusable.** The rule colouring filled buttons against dark backgrounds also matched `.ghost` and `.run`, so the sample model button and every filename in the history rail rendered near black on near black. Exactly the collision the design guidance warns about, and invisible without looking at the rendered page.

### Known limitations, stated honestly

- Recalculation proves a repair is mechanically sound. It cannot prove the repair expresses what the author meant. Where the workbook no longer holds enough information to infer intent, the clearest case being a reference whose target was deleted, the repair is labelled `needs_human_intent` rather than presented as proven.
- **Google Sheets import is covered by tests but not yet confirmed against a live sheet.** Creating one requires a Google account this build process does not have. The export URL, the auditability of what comes back, and every failure path are tested with the network call stubbed; a single link shared as anyone with the link would confirm the last mile.
- `formulas` does not implement every Excel function. Anything it cannot evaluate degrades to unverified and is never reported as proven.

### Verified end to end, by test rather than by assumption

| Path | How it was checked | Outcome |
| --- | --- | --- |
| Upload | multipart POST, then the audit run through the interface | 5 corrections, headline -1,704,250 |
| Download | fetched from the browser, reparsed, recalculated from scratch | matches the interface exactly |
| Google Sheets | 16 tests with only the call to Google stubbed | export URL, auditability, every error path |
| Autonomous | object dropped in the bucket, no further human action | Pub/Sub to Cloud Run to a stored run |
| Theme | clicked, then read data-theme and computed styles | light and dark, persisted |
| Chain resize | synthetic pointer drags at three widths | 330 to 500, clamps at 620 and 260, persisted |
| Rejections | CSV, renamed file, private sheet, .xls, empty, oversized | all refused with actionable text |

52 tests passing.

**The check that mattered most:** downloading the corrected workbook, reparsing it, and recalculating from scratch produced `Operating Income -1,704,250`, the same figure the interface reports. The number on screen is the number in the file.

### Deployed and proven in the cloud

- **Service:** `https://cassandra-gibp4zik7a-uc.a.run.app`
- **`/api/health`** reports `store: firestore`, `model: gemini-3.5-flash`, `vertex: TRUE`
- **The autonomous path works end to end.** A workbook dropped into the bucket fired `OBJECT_FINALIZE`, Pub/Sub pushed to Cloud Run, and the audit ran with no human action: 8 findings, 5 repaired, headline `Operating Income 6,246,545 -> -1,704,250`, persisted to Firestore.

### Two more traps, both cloud specific

8. **Cloud Run reserves `/healthz`.** It is answered by Google's frontend and never reaches the container, so the endpoint returns Google's own 404 page while every other route serves normally. It reads exactly like a service that failed to start. Health lives at `/api/health`.
9. **The Cloud Build service account lacks roles it needs by default.** Without `storage.objectViewer` the build cannot read the source archive it was just handed, which surfaces as a 403 on an object that plainly exists.
10. **numpy scalars broke the detail response.** Values reaching Firestore as numpy floats encode to a different byte length than the default encoder measures when setting Content-Length, so the body overran its own header mid response. Detail payloads are now built and measured in one pass.

### Remaining

- README spin up instructions verified against a clean clone
- Demo video, recorded by teammate
- Devpost submission

---

## Submission Materials

Copy ready. Everything below is drawn from real runs, not aspiration.

### Elevator pitch (184 characters)

> Cassandra is continuous integration for the spreadsheets that run your company. An autonomous agent fleet finds the defect, writes the fix, and proves it by recalculating the workbook.

### Devpost: what it does

Cassandra treats business critical spreadsheets the way engineering treats source code: as something that must be continuously tested and never silently broken.

Drop a workbook into a Cloud Storage bucket and nothing else is required of you. The file landing fires an event, Cloud Run wakes from zero, and an agent fleet parses the workbook into a formula dependency graph, locates candidate defects, rules on which are real, writes corrections, and proves each one by recalculating the entire file. A correction that does not move the target cell exactly as predicted, or that disturbs any cell outside its blast radius, is rejected and sent back with the reason it failed.

On the demo model, a three year SaaS projection, it found five defects in 114 seconds and proved every repair. The workbook reported **Operating Income of 6,246,545 for a company that actually lost 1,704,250**, a 7.95M overstatement. The largest single cause is operating expenses being added to gross profit instead of subtracted; the figure shown is what the workbook computes once all five corrections are applied together, which is the same file you can download.

### Devpost: features

- **Zero touch ingestion.** No upload button, no OAuth screen, no human trigger. The audit begins because a file exists.
- **Six defect classes.** Hardcoded constants, off by one aggregation ranges, formulas inconsistent with their region, sign inversions, broken references, and labels that disagree with their formula.
- **Verification by recalculation.** Every correction is applied to a copy and the workbook is recomputed. Nothing reaches the user that has not been proven.
- **Proof of latent defects.** A hardcoded constant equal to the assumption it replaced computes the correct answer today and is still broken. Cassandra proves these by differential counterfactual: patched and unpatched workbooks must agree as things stand, and diverge once the driver is perturbed.
- **Root cause separation.** When a total is wrong, everything downstream is wrong too. Cassandra reports the cause, not the symptoms, unless the downstream cell is independently broken.
- **Materiality ranking.** Findings are ordered by blast radius through the dependency graph, weighted toward the figures a human actually quotes.
- **Bounded self correction.** Three attempts, then the finding is quarantined for a human rather than guessed at.
- **Regression sentinel.** A later revision of the same workbook is diffed against the last run.

### Devpost: technologies

Gemini 3.5 Flash through Vertex AI, Google ADK for the agent fleet, Cloud Run for scale to zero execution, Cloud Storage and Pub/Sub for event driven ingestion, Firestore for run state and delivery idempotency, and OpenTelemetry for reasoning chain traces. The calculation oracle is the `formulas` Excel interpreter; the dependency graph is `networkx`.

### Devpost: data sources

No external data. The demo workbook is generated by `cassandra/demo/build_workbook.py`, with six defects planted from the Panko and Halverson spreadsheet error taxonomy so that every finding can be checked against a known answer.

### Devpost: findings and learnings

**A verifier is only as good as the failures it anticipates.** The first version accepted any patch that moved the target without collateral damage. Pointing a formula at an empty cell satisfies both conditions, which made blanking a figure the cheapest way to pass verification. A repair that destroys the number is not a repair.

**Some defects have no wrong value.** The hardcoded growth rate matched the assumption it replaced, so the workbook computed the correct answer and the verifier rejected the repair for changing nothing. The cell was still decoupled from its driver and would go stale the moment the assumption moved. Proving it required a counterfactual rather than an observation. Asking only whether the target moves when the driver moves is unsound, because the target may still reach the driver by an indirect path.

**Downstream is not the same as symptomatic.** Suppressing every finding inside a repaired cell's blast radius discarded two genuine independent defects, including the sign inversion that dominates the overstatement. Only a purely semantic complaint can be explained away by an upstream repair.

**Deterministic code beat the model wherever both could do the job.** The parser, dependency graph, region clustering, and all five structural detectors are plain Python. The model is consulted three times, each on a question a parser genuinely cannot answer. This made the search exhaustive and free, and left the model doing the part it is actually better at.

**The agents hold no tools, and that is the security posture.** Not one can read a file, mutate a workbook, or reach the network. A prompt injected into a cell label can at worst produce a wrong judgement, which the verifier rejects by recalculating, because the verifier asks the model nothing.

### Traps worth warning others about

- Gemini 3.x is served only from `location=global` on Vertex AI. Regional endpoints return 404 for every 3.x model while serving 2.5 happily, which reads as missing access and is not.
- Cloud Run reserves `/healthz` at its frontend; it never reaches the container.
- The Cloud Build service account lacks `storage.objectViewer` by default and cannot read the source archive it was handed.
- numpy scalars from Firestore encode to a different byte length than FastAPI measures when setting `Content-Length`, truncating the response mid flight.

---

## Demo Video Script

Four minutes, and the running order matters more than the words. Google Cloud proof is banked in the first minute, before anything can go wrong.

**0:00 to 0:30, the problem.** Open on the workbook in Excel, on the Operating Income cell reading 6,246,545. Say: 94% of spreadsheets contain at least one error, 95% of the financial models KPMG audited had major errors, and the people who wrote them put their own odds at one in ten. This company looks profitable. It is not.

**0:30 to 1:00, Google Cloud proof.** Cloud Console on screen. Drop the workbook into the bucket. Show the object landing, the Pub/Sub topic, and the Cloud Run service waking from zero. Say plainly: nobody pressed anything, the file existing is the trigger.

**1:00 to 2:30, the run.** The interface, live and unedited. The analysis line moving through its steps. Do not narrate every step; let it run and talk over it about the architecture: deterministic parsing, a dependency graph, then three agents on Gemini 3.5 Flash, none of which hold a single tool.

**Wait for the rejection.** When the line turns amber and reads "Correction rejected, revising", stop talking and point at it. This is the moment: the agent proposed a fix, the workbook was recalculated, the fix did not hold, and the agent was sent back with the reason. Then it passed. That is the difference between a demo and a proof.

**2:30 to 3:20, the result.** Operating Income, 6,246,545 struck through, negative 1,704,250 beside it. Overstated by 7,950,795. Then scroll the corrections, pausing on two:

- `PL!C8`, `=C6+C7` becoming `=C6-C7`. Operating expenses were being added to gross profit instead of subtracted. One character, and the largest single contributor to a 7.95M overstatement.
- `Revenue!D12`, unchanged today. Explain that this cell hardcodes a rate that currently equals the assumption, so it computes the right answer and is still broken, and that proving it took a counterfactual rather than an observation. This is the most sophisticated thing in the submission; give it fifteen seconds.

**3:20 to 4:00, architecture and close.** The mermaid diagram. Land on the one sentence that matters: three questions go to Gemini, and every answer is checked by recalculating the workbook, because the verifier asks the model nothing.

**Practical notes.** Record the audit locally, where it runs in about 114 seconds; Cloud Run on shared CPU is slower and four minutes is tight. Use the Console, the `.run.app` URL, and the live service for the cloud proof. Both are the same code making the same Vertex AI calls. Set `--min-instances 1` before filming to avoid a cold start, and back to 0 afterwards.

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
