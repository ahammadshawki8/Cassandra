# Demo video script

Four minutes. Two acts: why this exists, then watching it work.

The deck runs behind the narration for most of it. Three passages cut away to the live
product, and those are marked **LIVE** below. Every figure spoken here comes from a real
run, so nothing has to be staged.

- **Deck:** `docs/deck.html`, or open `/deck` on the running service. Arrow keys or space to
  advance, `F` for fullscreen, `G` to jump to a slide number.
- **Slide stills:** `screenshots/01-cold-open.png` through `screenshots/29-close.png`, if you
  would rather cut them in as images than screen record the deck.

---

## Before you record

- Deploy with `--min-instances 1` so there is no cold start. Set it back to `0` afterwards.
- Open four things: the Cloud Console storage browser, the Cassandra console at `/app`,
  Excel with `saas_projection_v11.xlsx`, and the deck fullscreen.
- Clear the history rail so it starts clean. The trash icon appears on row hover.
- Run the audit locally. It finishes in about 115 seconds; Cloud Run on shared CPU is
  slower and four minutes is tight.
- **Do not deploy while an audit is running.** A deploy replaces the revision and takes the
  in flight audit with it.
- For the regression section you need two runs in order: audit `saas_projection_v11.xlsx`
  first, then `saas_projection_v12.xlsx`. The sentinel only fires on a genuinely new
  revision.

---

## Act one · why this exists

### 0:00 · Slide 1 · cold open

> **SHOW:** `01-cold-open.png`, or cut to Excel with `saas_projection_v11.xlsx` open on the
> PL sheet, cell C8 selected so the formula bar reads `=C6+C7`.
>
> **Required by the rules, do not skip:** the video must show the backend running on
> Google Cloud. Four tabs cover it, all captured in the live segment at 1:58.
> Open them before you start recording:
>
> 1. Cloud Run service page: shows the .run.app URL, region, revision, and Serving traffic
> 2. Cloud Run LOGS tab, or Logs Explorer filtered to the cassandra service
> 3. Cloud Storage browser on the workbooks bucket
> 4. The Pub/Sub subscription, whose push endpoint reads .run.app/pubsub
>
> A fifth, free of charge: hit `/api/health` on the deployed URL for two seconds. It
> returns the project, the model, Vertex, and Firestore in a single frame.

"This company is reporting six point two million dollars of operating income."

> Pause. Do not speak over the number.

### 0:08 · Slide 2 · the reveal

> **ADVANCE** to `02-the-reveal.png` on the word "lost".

"It lost one point seven million. One character in one formula, and every number
downstream of it is wrong."

### 0:16 · Slide 3 · the problem

> **ADVANCE** on "untested".

"Spreadsheets are the largest untested codebase on earth. They allocate budgets, price
deals, and set national policy, and almost none of them are under test."

> Point at the highlighted cell in the grid on the right.

"A wrong formula looks exactly like a right one."

### 0:26 · Slide 4 · 94%

> **ADVANCE** on "ninety four".

"Ninety four percent of spreadsheets contain at least one error."

### 0:31 · Slide 5 · 95%

> **ADVANCE** on "ninety five".

"Ninety five percent of the financial models KPMG audited had major errors."

### 0:36 · Slide 6 · the gap

> **ADVANCE** on "why". Let both bars be on screen before the next sentence.

"And this is why none of it ever gets fixed. Ask the people who build these models how
often they make a mistake and they say fourteen percent. The measured rate is eighty six."

### 0:46 · Slide 7 · the line

> **ADVANCE** on "Nobody". Hold this slide for the full sentence, then one beat of silence.

"Nobody audits a spreadsheet, because nobody believes theirs is the broken one."

### 0:53 · Slide 8 · it has happened before

> **ADVANCE** on "Reinhart".

"Reinhart and Rogoff shaped austerity policy across the developed world off a sum that
omitted five rows. JPMorgan's London Whale loss involved a copy and paste error inside a
six and a half billion dollar hole."

### 1:02 · Slide 9 · Cassandra

> **ADVANCE** on the name.

"Cassandra is continuous integration for the spreadsheets that run your company."

### 1:07 · Slide 10 · it starts itself

> **ADVANCE** on "does not wait".

"It does not wait to be asked. A workbook lands in a bucket and the fleet wakes up on its
own."

### 1:14 · Slide 11 · the five steps

> **ADVANCE** on "maps". Point at each card as you name it.

"It maps the model into a formula dependency graph, hunts for candidates, judges which are
real, and then two steps that no other tool has."

### 1:24 · Slide 12 · three questions

> **ADVANCE** on "three".

"Three questions go to Gemini three point five Flash. Does this formula compute what its
label claims. Is this a defect or a legitimate modelling choice. And what is the correct
repair. Everything else is deterministic code."

### 1:36 · Slide 13 · it proves the fix

> **ADVANCE** on "does not show you".

"And this is what makes it different from every spreadsheet tool that already exists. It
does not show you the fix. It applies the fix to a copy, recalculates the entire workbook,
and asks two questions: did the target move exactly as predicted, and did anything move
that should not have. Either answer wrong and the correction is rejected."

### 1:50 · Slide 14 · the guarantee

> **ADVANCE** on "asks the model nothing". Hold.

"The Verifier asks the model nothing. Nothing reaches you that the system has not first
proven to itself."

---

## Act two · watching it work

One continuous story. Do not jump between features.

### 1:58 · Slide 15, then **LIVE** · the bucket

> **ADVANCE** to slide 15, speak the first line, then **CUT TO THE CLOUD CONSOLE.**
> Drag `saas_projection_v11.xlsx` into the bucket. Show the object appear, then the
> Pub/Sub topic, then the Cloud Run service with its revision and `.run.app` URL visible.

"A file lands in a bucket. Nobody presses anything. Cloud Storage fires an event, Pub/Sub
delivers it, and Cloud Run wakes from zero."

### 2:10 · **LIVE** · the fleet works

> **STAY LIVE.** Switch to the Cassandra console. The reasoning chain on the right is
> streaming. Do not narrate every line.

"Every step the agents take is on the right as it happens."

> When the blue semantic mismatch lines appear, slow down. Optionally **CUT TO SLIDE 16**
> for eight seconds if you want the detail readable, then back.

"Here is the semantic auditor doing something no static analyzer can. This cell is
labelled Operating Income. It computes gross profit plus operating expenses. The label and
the formula disagree, and only a model that reads English catches that."

### 2:28 · **LIVE** · the rejection

> **STAY LIVE.** When the progress header turns amber and reads "Correction rejected,
> revising", **stop talking and hold for two full seconds.** This is the most important
> moment in the video. Optionally cut to slide 17 to make the line readable.

"And there it is. The agent proposed a fix. The workbook was recalculated. The fix did not
hold, so it was rejected and sent back with the reason it failed."

> Then, as the next attempt goes green:

"Second attempt. Proven."

### 2:42 · **LIVE** · the result

> **STAY LIVE** on the headline card. Slide 19 is the same figures if you need a clean
> frame instead.

"Eight findings. Five corrections, every one proven by recalculation. And the number this
company would have taken to its board goes from six point two million of profit to a one
point seven million loss."

> Scroll to `PL!C8`. Cut to **slide 20** for the diff if the browser text is small.

"Operating expenses added to gross profit instead of subtracted. One character."

### 2:56 · Slide 21 · the latent defect

> **CUT TO SLIDE 21.** This is the most sophisticated finding in the project, so give it
> the clean frame rather than fighting the browser.

"And this one I would put in front of any auditor. This cell hardcodes a growth rate that
currently happens to equal the assumption. The number is correct today. It is still
broken, because it has been cut off from its driver and goes stale the moment anybody
updates that assumption. Cassandra proves it by changing the driver and showing the
patched and unpatched workbooks diverge. A defect that has no wrong value yet."

### 3:10 · Slide 22, then **LIVE** · the corrected file

> **ADVANCE** to slide 22, then **CUT LIVE**: click Download corrected workbook, open the
> file in Excel, select `PL!C8` so the formula bar shows `=C6-C7`, and show Operating
> Income reading `-1,704,250`.

"And this is not a report. It is the repaired workbook, with every proven correction
applied and everything uncertain deliberately left alone. Recalculate it yourself. The
number on the screen is the number in the file."

### 3:22 · Slide 23, then **LIVE** · the regression

> **ADVANCE** to slide 23. **CUT LIVE** to the history rail showing `saas_projection_v11`
> above `saas_projection_v12`. Open the v12 run so the amber "Newly broken in this
> revision" banner is visible.

"Now the next revision of the same model. Every defect from last week has been repaired,
and somebody has typed a twelve percent uplift straight into a revenue cell. Cassandra
pairs the two revisions and reports only what is new. This is the question no spreadsheet
tool on the market answers: this was fine last week, what broke since."

### 3:36 · Slide 24 · nothing is wrong

> **ADVANCE** on "one more". If you have the time, drop `clean_amortisation.xlsx` live.

"One more. A correct loan schedule, a hundred and twenty three formulas, nothing wrong
with it. Nothing reported. It examined one cell that looked unusual, worked out it was a
legitimate series seed, and stayed quiet. A tool that cries wolf on a healthy model is
worse than no tool at all."

---

## The close

### 3:46 · Slide 25 · architecture

> **ADVANCE** on "three questions".

"Three questions go to Gemini. Everything else, including the verification that decides
whether the model was right, is deterministic code."

### 3:51 · Slide 26 · no tools

> **ADVANCE** on "hold no tools".

"The agents hold no tools at all. Not one can read a file, change a workbook, or reach the
network, so the worst a prompt injected into a cell label can do is cause a wrong
judgement that recalculation then rejects."

### 3:56 · Slide 29 · close

> **JUMP TO SLIDE 29** and hold to the end. Skip 27 and 28 unless you are running short of
> content; they are there as spares.

"Cassandra does not wait. It finds the defect, writes the fix, and proves it. And it will
not tell you a single thing it has not proven first."

---

## Slide map

| Slide | File | Where it appears |
| --- | --- | --- |
| 1 | `01-cold-open.png` | 0:00 |
| 2 | `02-the-reveal.png` | 0:08 |
| 3 | `03-the-problem.png` | 0:16 |
| 4 | `04-stat-94.png` | 0:26 |
| 5 | `05-stat-95.png` | 0:31 |
| 6 | `06-the-gap.png` | 0:36 |
| 7 | `07-nobody-believes.png` | 0:46 |
| 8 | `08-it-has-happened.png` | 0:53 |
| 9 | `09-cassandra.png` | 1:02 |
| 10 | `10-starts-itself.png` | 1:07 |
| 11 | `11-five-steps.png` | 1:14 |
| 12 | `12-three-questions.png` | 1:24 |
| 13 | `13-proves-the-fix.png` | 1:36 |
| 14 | `14-verifier-asks-nothing.png` | 1:50 |
| 15 | `15-live-bucket.png` | 1:58, then live |
| 16 | `16-live-semantic.png` | 2:10, optional cutaway |
| 17 | `17-live-rejection.png` | 2:28, optional cutaway |
| 18 | `18-live-proven.png` | 2:38, optional cutaway |
| 19 | `19-the-result.png` | 2:42, spare for the live headline |
| 20 | `20-one-character.png` | 2:50 |
| 21 | `21-latent-defect.png` | 2:56 |
| 22 | `22-corrected-file.png` | 3:10, then live |
| 23 | `23-regression.png` | 3:22, then live |
| 24 | `24-zero-findings.png` | 3:36 |
| 25 | `25-architecture.png` | 3:46 |
| 26 | `26-no-tools.png` | 3:51 |
| 27 | `27-research.png` | spare |
| 28 | `28-comparison.png` | spare |
| 29 | `29-close.png` | 3:56, hold to end |

## Live segments, in order

1. **1:58 to 2:10** · Cloud Console: drop the file in the bucket, show Pub/Sub and Cloud Run
2. **2:10 to 2:56** · the console: reasoning chain, the rejection, the result
3. **3:10 to 3:22** · download the corrected workbook and open it in Excel
4. **3:22 to 3:36** · the history rail and the newly broken banner

Everything else is the deck.

## Three lines to rehearse

These are the ones that will be remembered.

- "Nobody audits a spreadsheet, because nobody believes theirs is the broken one."
- "The fix did not hold, so it was rejected and sent back with the reason it failed."
- "It will not tell you a single thing it has not proven first."
