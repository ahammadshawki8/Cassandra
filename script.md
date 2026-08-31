## Demo Video Script

Four minutes. Two acts: why this exists, then watching it work. Every number and every screen below comes from a real run, so nothing has to be staged.

### Before you record

- Deploy with `--min-instances 1` so there is no cold start, and set it back to 0 afterwards.
- Have four things open in tabs: the Cloud Console storage browser, the Cassandra console at `/app`, Excel with `saas_projection_v11.xlsx`, and the landing page at `/`.
- Delete old runs from the history rail so it starts clean. The trash icon appears on hover.
- Record the audit locally. It finishes in about 115 seconds there; Cloud Run on shared CPU is slower and four minutes is tight.
- Record in one take per act if you can. The rubric rewards unedited execution, and the loop is more convincing when nobody could have cut anything out.

---

### Act one: why this exists (0:00 to 1:10)

**0:00 to 0:12 — the hook**

> ON SCREEN: Excel, full screen, `saas_projection_v11.xlsx` open on the PL sheet. Cell C8 selected so the formula bar reads `=C6+C7`. Zoom the Operating Income row so `6,246,545` fills the frame.

"This company is reporting six point two million dollars of operating income."

> ON SCREEN: hold on the number for a beat. Do not speak over the pause.

"It lost one point seven million. One character in one formula, and every number downstream of it is wrong."

**0:12 to 0:30 — why nobody catches it**

> ON SCREEN: cut to the landing page problem section. Let the bars fill on scroll: 94, 95, 86, then the short blue 14 percent bar.

"Ninety four percent of spreadsheets contain at least one error. Ninety five percent of the financial models KPMG audited had major ones."

> ON SCREEN: hold on the fourth bar, the short one.

"And this is the reason none of it ever gets fixed. When you ask the people who built those models how often they make a mistake, they say fourteen percent. The measured rate is eighty six. Nobody audits a spreadsheet, because nobody believes theirs is the broken one."

**0:30 to 1:10 — the idea**

> ON SCREEN: landing page, the five step pipeline. Let each node land as you name it.

"So Cassandra does not wait to be asked. A workbook lands in a bucket, and a fleet of agents wakes up on its own."

> ON SCREEN: scroll to the architecture diagram. Point at each lane as you say it.

"It parses the model into a formula dependency graph. That part is plain Python, because a parser does it better than a language model ever will. Then Gemini three point five Flash is asked the three questions a parser genuinely cannot answer. Does this formula compute what its label claims. Is this a real defect or a legitimate modelling choice. And what is the correct repair."

> ON SCREEN: scroll to the Verifier lane, the green one. Hold on it.

"And then the part that makes this different from every spreadsheet tool that already exists. It does not show you the fix. It applies the fix to a copy, recalculates the entire workbook, and checks two things: did the target move exactly as predicted, and did anything move that should not have. If either answer is wrong, the correction is rejected and sent back."

> ON SCREEN: the two column trust panel, never asks the model / asks the model.

"The Verifier asks the model nothing. Nothing reaches you that the system has not first proven to itself."

---

### Act two: watching it work (1:10 to 3:25)

One continuous story. Do not jump between features.

**1:10 to 1:30 — it starts on its own**

> ON SCREEN: Google Cloud Console, the bucket. Drag `saas_projection_v11.xlsx` into it. Show the object appear.

"Nobody presses anything. The file existing is the trigger."

> ON SCREEN: Cloud Console, quickly: the Pub/Sub topic, then the Cloud Run service with its revision and the `.run.app` URL visible.

"Cloud Storage fires an event, Pub Sub delivers it, and Cloud Run wakes from zero."

**1:30 to 2:20 — the fleet works, and fails, and recovers**

> ON SCREEN: switch to the Cassandra console. The reasoning chain on the right is streaming. Do not narrate every line.

"Every step is on the right as it happens. Parsing, the dependency graph, then the detectors."

> ON SCREEN: as the blue semantic mismatch lines appear, slow down.

"Here is the semantic auditor doing something no static analyzer can. This cell is labelled Operating Income. It computes gross profit plus operating expenses. The label and the formula disagree, and only a model that can read English catches that."

> ON SCREEN: the amber line. When the progress header turns amber and reads "Correction rejected, revising", stop talking and let it sit for two full seconds.

"And there it is. The agent proposed a fix. The workbook was recalculated. The fix did not hold, so it was rejected and sent back with the reason it failed."

> ON SCREEN: the next attempt going green.

"Second attempt. Proven."

**2:20 to 2:50 — the result**

> ON SCREEN: the headline card. `6,246,545` struck through beside `-1,704,250`.

"Eight findings. Five corrections, every one proven by recalculation. And the number this company would have taken to its board goes from six point two million of profit to a one point seven million loss."

> ON SCREEN: scroll slowly through the corrections. Pause on `PL!C8`.

"Operating expenses added to gross profit instead of subtracted. One character."

> ON SCREEN: pause on `Revenue!D12`, and hold on the amber badge that reads "unchanged today, diverges the moment the assumption moves".

"And this one is the finding I would put in front of any auditor. This cell hardcodes a growth rate that currently happens to equal the assumption. The number is correct today. It is still broken, because it has been cut off from its driver and goes stale the moment anybody updates that assumption. Cassandra proves it by changing the driver and showing the patched and unpatched workbooks diverge. It is a defect that has no wrong value yet, and no static checker on the market can find it."

**2:50 to 3:10 — you get the fixed file**

> ON SCREEN: click Download corrected workbook. Open the downloaded file in Excel. Select PL!C8 so the formula bar shows `=C6-C7`. Show Operating Income reading `-1,704,250`.

"And this is not a report. It is the repaired workbook, with every proven correction applied and everything uncertain deliberately left alone. Recalculate it yourself. The number on the screen is the number in the file."

**3:05 to 3:18 — it knows what you broke since last week**

> ON SCREEN: the history rail, showing `saas_projection_v11.xlsx` above `saas_projection_v12.xlsx`. Open the v12 run. The amber "Newly broken in this revision" banner is at the top.

"Now the next revision of the same model. Every defect from last week has been repaired, and somebody has typed a twelve percent uplift straight into a revenue cell."

> ON SCREEN: hold on the banner reading `Revenue!D6 is newly broken in this revision`.

"Cassandra pairs the two revisions and reports only what is new. This is the question no spreadsheet tool on the market answers: this was fine last week, what broke since."

**3:18 to 3:30 — it knows when to say nothing**

> ON SCREEN: back in the console, drop `clean_amortisation.xlsx` onto the drop zone. Let it run, sped up if you need the time.

"One more. This is a correct loan schedule. A hundred and twenty three formulas, nothing wrong with it."

> ON SCREEN: the result: no headline, nothing reported, the single candidate shown as examined and left alone.

"Nothing reported. It examined one cell that looked unusual, worked out it was a legitimate series seed, and stayed quiet. A tool that cries wolf on a healthy model is worse than no tool at all."

---

### The close (3:30 to 4:00)

> ON SCREEN: the architecture diagram again, full width, then hold.

"Three questions go to Gemini. Everything else, including the verification that decides whether the model was right, is deterministic code. The agents hold no tools at all. Not one of them can read a file, change a workbook, or reach the network, so the worst a prompt injected into a cell label can do is cause a wrong judgement that recalculation then rejects."

> ON SCREEN: cut back to Excel, the original `6,246,545`, then hard cut to the corrected `-1,704,250`.

"Spreadsheets are the largest untested codebase on earth. They set budgets, price deals, and shape national policy, and almost none of them are under test, because testing them by hand is unbearable and every existing tool waits for a human who never comes."

> ON SCREEN: the Cassandra landing page hero, held to the end.

"Cassandra does not wait. It finds the defect, writes the fix, and proves it. And it will not tell you a single thing it has not proven first."

> FINAL FRAME: the mark and the wordmark, with the live URL beneath it.

---

### Shot list, in order

1. Excel, PL!C8 selected, Operating Income at 6,246,545
2. Landing page, the four bars filling
3. Landing page, the five step pipeline
4. Landing page, the architecture lanes, ending on the green Verifier
5. Landing page, the two column trust panel
6. Cloud Console, dropping the file into the bucket
7. Cloud Console, Pub/Sub topic and Cloud Run revision with the run.app URL
8. Console, reasoning chain streaming
9. Console, the amber rejection, held for two seconds
10. Console, the headline card
11. Console, PL!C8 correction
12. Console, Revenue!D12 with the latent badge
13. Excel, the downloaded corrected workbook recalculating
14. Console, the v11 and v12 history rail with the newly broken banner
15. Console, the clean workbook returning nothing
16. Landing page hero, final frame

### Lines to get exactly right

These three are the ones that will be remembered. Rehearse them.

- "Nobody audits a spreadsheet, because nobody believes theirs is the broken one."
- "The fix did not hold, so it was rejected and sent back with the reason it failed."
- "It will not tell you a single thing it has not proven first."

---

