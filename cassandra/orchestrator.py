"""The audit run: deterministic control flow around probabilistic judgement.

The loop itself is plain Python. Agents are consulted at exactly three points,
each one a question a parser genuinely cannot answer, and every answer they give
is either checked by recalculation or discarded.

  parse and map        deterministic
  detect candidates    deterministic
  read labels          Semantic Auditor
  rule on candidates   Adjudicator
  write the repair     Patcher
  prove the repair     deterministic, and final

Putting the loop in code rather than in an agent is the difference between a
system that fails predictably and one that wanders. There is no path here by
which a model decides what happens next.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable

from .agents import fleet
from .agents.schemas import Adjudication, ProposedPatch, SemanticReport
from .core import detectors, graph, oracle, parser, regions
from .core.detectors import Finding

MAX_PATCH_ATTEMPTS = 3

# A driver is perturbed by this factor to prove a latent defect. The value is
# arbitrary; it only has to be large enough to move the number visibly.
LATENT_PERTURBATION = 1.75


class Status(str, Enum):
    DETECTED = "detected"
    DISMISSED = "dismissed"
    CONFIRMED = "confirmed"
    REPAIRED = "repaired"
    QUARANTINED = "quarantined"
    RESOLVED_UPSTREAM = "resolved_upstream"


def _referenced_cells(formula: str, default_sheet: str) -> set[str]:
    """Every cell a formula reads, expanded from its ranges."""
    from .core.refs import parse_refs

    out: set[str] = set()
    for ref in parse_refs(formula):
        out.update(ref.cells(default_sheet))
    return out


@dataclass
class PatchAttempt:
    """One trip around the patch and verify loop, kept whether or not it passed."""

    attempt: int
    formula: str
    predicted: Any
    passed: bool
    reason: str
    rationale: str = ""
    latent: bool = False


@dataclass
class Result:
    """A single finding, carried from detection through to its final state."""

    cell: str
    detector: str
    defect_class: str
    status: Status
    detector_confidence: float
    impact: float
    blast_radius: list[str] = field(default_factory=list)
    summary: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    severity: str = ""
    agent_confidence: float = 0.0
    explanation: str = ""
    dismissal_reason: str = ""

    attempts: list[PatchAttempt] = field(default_factory=list)
    final_formula: str = ""
    original_formula: str = ""
    value_before: Any = None
    value_after: Any = None
    downstream_moved: list[dict[str, Any]] = field(default_factory=list)

    # Recalculation proves a repair is mechanically sound. It cannot prove the
    # repair expresses what the author meant. Where the workbook no longer
    # contains enough information to infer intent, the clearest case being a
    # reference whose target has been deleted, the repair is a proposal and is
    # labelled as one rather than presented as proven.
    needs_human_intent: bool = False

    @property
    def materiality(self) -> float:
        """Ranking score: consequence weighted by how sure we are."""
        weight = {"critical": 4.0, "material": 2.0, "minor": 0.5, "cosmetic": 0.1}
        return (
            max(self.impact, 1.0)
            * weight.get(self.severity, 1.0)
            * max(self.agent_confidence, self.detector_confidence)
        )


@dataclass
class AuditRun:
    """Everything one audit produced, serializable for storage and the UI."""

    run_id: str
    workbook: str
    started_at: float
    finished_at: float = 0.0
    sheets: list[str] = field(default_factory=list)
    cell_count: int = 0
    formula_count: int = 0
    region_count: int = 0
    results: list[Result] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)
    headline: dict[str, Any] = field(default_factory=dict)
    grid: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        payload = asdict(self)
        payload["results"] = [
            {**asdict(r), "status": r.status.value, "materiality": r.materiality}
            for r in self.results
        ]
        return json.dumps(payload, indent=2, default=str)


TraceSink = Callable[[dict[str, Any]], None]


class Auditor:
    """Runs one workbook through the whole pipeline."""

    def __init__(self, on_event: TraceSink | None = None, use_agents: bool = True):
        self.on_event = on_event or (lambda _: None)
        self.use_agents = use_agents
        self._agents: dict[str, Any] = {}

    def _agent(self, name: str):
        if name not in self._agents:
            builder = {
                "adjudicator": fleet.build_adjudicator,
                "patcher": fleet.build_patcher,
                "semantic": fleet.build_semantic_auditor,
            }[name]
            self._agents[name] = builder()
        return self._agents[name]

    def _emit(self, run: AuditRun, kind: str, message: str, **extra: Any) -> None:
        event = {"t": round(time.time() - run.started_at, 3), "kind": kind,
                 "message": message, **extra}
        run.trace.append(event)
        self.on_event(event)

    def _ask(self, run: AuditRun, name: str, prompt: str, model_cls):
        """Consult an agent and parse its structured reply, or give up cleanly."""
        try:
            raw = fleet.ask(self._agent(name), prompt)
            return model_cls.model_validate_json(raw)
        except Exception as exc:
            self._emit(
                run, "agent_error",
                f"{name} did not return a usable answer: {type(exc).__name__}",
            )
            return None

    def audit(self, path: str) -> AuditRun:
        run = AuditRun(
            run_id=uuid.uuid4().hex[:12], workbook=path, started_at=time.time()
        )

        self._emit(run, "start", f"opening {path}")
        book = parser.parse(path)
        run.sheets = list(book.sheets)
        run.cell_count = len(book.cells)
        run.formula_count = len(book.formula_cells)
        self._emit(
            run, "parsed",
            f"{run.cell_count} cells across {len(run.sheets)} sheets, "
            f"{run.formula_count} of them formulas",
        )

        dag = graph.build(book)
        outputs = graph.output_cells(dag, book)
        self._emit(
            run, "mapped",
            f"dependency graph built, {dag.number_of_edges()} edges, "
            f"{len(outputs)} terminal output figures",
        )

        clusters = regions.cluster(book)
        run.region_count = len(clusters)
        outlier_count = sum(len(r.outliers) for r in clusters)
        self._emit(
            run, "clustered",
            f"{len(clusters)} regions, {outlier_count} cells break their region's pattern",
        )

        baseline = oracle.calculate(path, run.sheets)
        if "__workbook__" in baseline.errors:
            self._emit(run, "fatal", f"workbook will not calculate: {baseline.errors['__workbook__']}")
            run.finished_at = time.time()
            return run
        self._emit(run, "baseline", f"baseline calculated, {len(baseline.values)} cell values")

        findings = detectors.run_all(book, dag, clusters, baseline.values)
        self._emit(run, "detected", f"{len(findings)} candidate defects located", count=len(findings))

        if self.use_agents:
            findings.extend(self._semantic_pass(run, book, dag, baseline))

        # Deduplicate: the semantic auditor and a structural detector routinely
        # describe the same cell from two angles. Keep the stronger signal.
        findings = self._merge(findings)

        # Handle root causes before their symptoms. A finding that sits in the
        # blast radius of another is very often not independently broken, it is
        # simply reporting the upstream defect faithfully.
        upstream: set[str] = set()
        for finding in findings:
            upstream.update(finding.blast_radius)
        findings.sort(
            key=lambda f: (f.cell in upstream, -(f.confidence * max(f.impact, 1.0)))
        )

        repaired_cells: set[str] = set()
        for finding in findings:
            # Only a purely semantic complaint can be explained away by an
            # upstream repair. If a structural detector read this cell's own
            # formula and objected, the cell is independently broken and must be
            # judged on its own, however healthy its inputs have become.
            symptom_of = None
            if not finding.is_structural:
                symptom_of = next(
                    (
                        r.cell for r in run.results
                        if r.status is Status.REPAIRED and finding.cell in r.blast_radius
                    ),
                    None,
                )
            if symptom_of:
                self._emit(
                    run, "resolved_upstream",
                    f"{finding.cell} needs no repair of its own: it reported the "
                    f"defect at {symptom_of} faithfully and is correct now that "
                    f"{symptom_of} is fixed",
                    cell=finding.cell,
                )
                run.results.append(
                    Result(
                        cell=finding.cell,
                        detector=finding.detector,
                        defect_class=finding.defect_class,
                        status=Status.RESOLVED_UPSTREAM,
                        detector_confidence=finding.confidence,
                        impact=finding.impact,
                        blast_radius=finding.blast_radius,
                        summary=finding.summary,
                        evidence=finding.evidence,
                        explanation=f"downstream of {symptom_of}, resolved by that repair",
                        value_before=baseline.values.get(finding.cell),
                    )
                )
                continue

            result = self._process(run, finding, path, book, dag, baseline)
            run.results.append(result)
            if result.status is Status.REPAIRED:
                repaired_cells.add(result.cell)

        run.results.sort(key=lambda r: -r.materiality)
        run.headline = self._headline(run, book, baseline)
        run.grid = self._grid(book, baseline)
        run.finished_at = time.time()
        self._emit(
            run, "done",
            f"{sum(1 for r in run.results if r.status is Status.REPAIRED)} repairs verified, "
            f"{sum(1 for r in run.results if r.status is Status.QUARANTINED)} quarantined, "
            f"{sum(1 for r in run.results if r.status is Status.DISMISSED)} dismissed",
        )
        return run

    def _semantic_pass(self, run, book, dag, baseline) -> list[Finding]:
        """One batched model call over every labelled formula cell."""
        candidates = detectors.semantic_candidates(book)
        if not candidates:
            return []

        lines = []
        for c in candidates[:40]:
            value = baseline.values.get(c.cell, c.evidence.get("value"))
            lines.append(
                f"{c.cell} | label: {c.evidence['label']} | formula: "
                f"{c.evidence['formula']} | value: {value}"
            )
        prompt = (
            "Check each cell below. Return a verdict for every one.\n\n"
            + "\n".join(lines)
        )
        self._emit(run, "agent", f"semantic auditor reading {len(lines)} labelled cells")

        report = self._ask(run, "semantic", prompt, SemanticReport)
        if report is None:
            return []

        out: list[Finding] = []
        for verdict in report.verdicts:
            if verdict.agrees_with_label or verdict.confidence < 0.5:
                continue
            cell = book.get(verdict.cell)
            if cell is None:
                continue
            finding = Finding(
                cell=verdict.cell,
                detector="semantic_auditor",
                defect_class="formula does not compute what its label claims",
                confidence=verdict.confidence,
                summary=verdict.explanation,
                evidence={
                    "formula": cell.formula,
                    "label": cell.label,
                    "actually computes": verdict.what_it_actually_computes,
                },
            )
            finding.blast_radius = sorted(graph.blast_radius(dag, verdict.cell))
            finding.impact = graph.impact_score(dag, book, verdict.cell)
            out.append(finding)
            self._emit(
                run, "agent_finding",
                f"semantic mismatch at {verdict.cell}: labelled "
                f"{cell.label!r} but computes {verdict.what_it_actually_computes}",
                cell=verdict.cell,
            )
        return out

    def _merge(self, findings: list[Finding]) -> list[Finding]:
        """One finding per cell, keeping the strongest signal and pooling evidence."""
        best: dict[str, Finding] = {}
        for finding in findings:
            existing = best.get(finding.cell)
            if existing is None:
                best[finding.cell] = finding
                continue
            keep, drop = (
                (finding, existing)
                if finding.confidence > existing.confidence
                else (existing, finding)
            )
            keep.evidence.setdefault("also flagged by", drop.detector)
            keep.evidence.setdefault("second observation", drop.summary)
            keep.detectors = keep.detectors | drop.detectors
            best[finding.cell] = keep
        return list(best.values())

    def _sane(self, run, result, proposal, book) -> str:
        """Reject a proposal on inspection, before spending a recalculation on it.

        The patcher occasionally invents a reference just outside the used range,
        which is cheap to catch by reading the formula and expensive to catch by
        calculating the workbook.
        """
        formula = (proposal.formula or "").strip()
        if not formula.startswith("="):
            return "a formula must begin with an equals sign"
        if formula == (result.original_formula or "").strip():
            return "the proposed formula is identical to the original"

        sheet = result.cell.split("!", 1)[0]
        unknown = [
            ref for ref in sorted(_referenced_cells(formula, sheet))
            if book.get(ref) is None
        ]
        if unknown:
            return (
                f"references {', '.join(unknown[:3])}, which "
                f"{'do' if len(unknown) > 1 else 'does'} not exist in this workbook"
            )
        return ""

    def _process(self, run, finding, path, book, dag, baseline) -> Result:
        cell = book.get(finding.cell)
        result = Result(
            cell=finding.cell,
            detector=finding.detector,
            defect_class=finding.defect_class,
            status=Status.DETECTED,
            detector_confidence=finding.confidence,
            impact=finding.impact,
            blast_radius=finding.blast_radius,
            summary=finding.summary,
            evidence=finding.evidence,
            original_formula=(cell.formula if cell else "") or "",
            value_before=baseline.values.get(finding.cell),
        )

        if not self.use_agents:
            return result

        ruling = self._ask(run, "adjudicator", finding.to_prompt(), Adjudication)
        if ruling is None:
            result.status = Status.QUARANTINED
            result.explanation = "the adjudicator could not be reached"
            return result

        result.severity = ruling.severity
        result.agent_confidence = ruling.confidence
        result.explanation = ruling.explanation

        if not ruling.is_defect:
            result.status = Status.DISMISSED
            result.dismissal_reason = ruling.dismissal_reason
            self._emit(
                run, "dismissed",
                f"{finding.cell} dismissed: {ruling.dismissal_reason}",
                cell=finding.cell,
            )
            return result

        result.status = Status.CONFIRMED
        self._emit(
            run, "confirmed",
            f"{finding.cell} confirmed {ruling.severity}: {ruling.explanation}",
            cell=finding.cell, severity=ruling.severity,
        )

        return self._repair(run, result, finding, path, book, dag, baseline)

    def _repair(self, run, result, finding, path, book, dag, baseline) -> Result:
        """The patch and verify loop. Bounded, and it quarantines rather than guessing."""
        radius = set(finding.blast_radius)
        rejections: list[str] = []

        for attempt in range(1, MAX_PATCH_ATTEMPTS + 1):
            prompt = finding.to_prompt()
            prompt += f"\n\nthe adjudicator ruled: {result.explanation}"
            if rejections:
                prompt += (
                    "\n\nyour previous attempts were rejected by recalculating "
                    "the workbook. do not repeat them:\n"
                    + "\n".join(f"  - {r}" for r in rejections)
                )

            self._emit(
                run, "patching",
                f"patcher attempt {attempt} of {MAX_PATCH_ATTEMPTS} for {finding.cell}",
                cell=finding.cell, attempt=attempt,
            )
            proposal = self._ask(run, "patcher", prompt, ProposedPatch)
            if proposal is None:
                rejections.append("the patcher returned nothing usable")
                continue

            objection = self._sane(run, result, proposal, book)
            if objection:
                result.attempts.append(
                    PatchAttempt(
                        attempt=attempt, formula=proposal.formula,
                        predicted=proposal.predicted_value, passed=False,
                        reason=objection, rationale=proposal.rationale,
                        latent=proposal.is_latent,
                    )
                )
                rejections.append(f"{proposal.formula} rejected because it {objection}")
                self._emit(
                    run, "rejected",
                    f"{finding.cell} attempt {attempt} rejected on inspection: {objection}",
                    cell=finding.cell, attempt=attempt, formula=proposal.formula,
                )
                continue

            verdict = self._prove(path, result, proposal, radius, baseline, run.sheets)

            result.attempts.append(
                PatchAttempt(
                    attempt=attempt,
                    formula=proposal.formula,
                    predicted=proposal.predicted_value,
                    passed=verdict.passed,
                    reason=verdict.reason,
                    rationale=proposal.rationale,
                    latent=proposal.is_latent,
                )
            )

            if verdict.passed:
                result.status = Status.REPAIRED
                result.final_formula = proposal.formula
                result.needs_human_intent = "broken reference" in result.defect_class
                result.value_after = verdict.observed
                result.downstream_moved = [
                    {"cell": d.key, "before": d.before, "after": d.after}
                    for d in verdict.intended_deltas
                    if d.key != result.cell
                ]
                self._emit(
                    run, "verified",
                    f"{finding.cell} "
                    + ("repaired, but the original intent cannot be recovered from "
                       "the workbook so this needs a human to confirm: "
                       if result.needs_human_intent else "repaired and proven: ")
                    + proposal.formula,
                    cell=finding.cell, formula=proposal.formula,
                    moved=len(result.downstream_moved),
                )
                return result

            rejections.append(f"{proposal.formula} rejected because {verdict.reason}")
            self._emit(
                run, "rejected",
                f"{finding.cell} attempt {attempt} rejected: {verdict.reason}",
                cell=finding.cell, attempt=attempt, formula=proposal.formula,
            )

        result.status = Status.QUARANTINED
        self._emit(
            run, "quarantined",
            f"{finding.cell} could not be repaired in {MAX_PATCH_ATTEMPTS} attempts, "
            f"raised for a human",
            cell=finding.cell,
        )
        return result

    def _prove(self, path, result, proposal, radius, baseline, sheets):
        """Route to direct or counterfactual verification, as the patch requires."""
        if proposal.is_latent and proposal.driver_cell:
            current = baseline.values.get(proposal.driver_cell)
            if isinstance(current, (int, float)) and not isinstance(current, bool):
                return oracle.verify_latent(
                    path, result.cell, proposal.formula, proposal.driver_cell,
                    current * LATENT_PERTURBATION, baseline, sheets,
                )
        return oracle.verify(
            path, result.cell, proposal.formula, proposal.predicted_value,
            radius, baseline, sheets,
        )

    def _grid(self, book, baseline) -> dict[str, Any]:
        """A compact rendering of the workbook for the dashboard."""
        sheets: dict[str, Any] = {}
        for name, sheet in book.sheets.items():
            cells = {}
            for key, cell in sheet.cells.items():
                cells[key.split("!", 1)[1]] = {
                    "r": cell.ref.row,
                    "c": cell.ref.col,
                    "f": cell.formula,
                    "v": baseline.values.get(key, cell.value),
                    "l": cell.label,
                    "fmt": cell.number_format,
                }
            sheets[name] = {
                "rows": sheet.max_row,
                "cols": sheet.max_col,
                "cells": cells,
            }
        return sheets

    def _headline(self, run, book, baseline) -> dict[str, Any]:
        """The single number a reader of this model would quote, and its fate."""
        repaired = [r for r in run.results if r.status is Status.REPAIRED]
        moved: dict[str, dict[str, Any]] = {}
        for result in repaired:
            for delta in result.downstream_moved:
                moved[delta["cell"]] = delta
            if result.value_before is not None:
                moved[result.cell] = {
                    "cell": result.cell,
                    "before": result.value_before,
                    "after": result.value_after,
                }

        def swing(entry: dict[str, Any]) -> float:
            before, after = entry.get("before"), entry.get("after")
            if isinstance(before, (int, float)) and isinstance(after, (int, float)):
                return abs(after - before)
            return 0.0

        if not moved:
            return {}
        worst = max(moved.values(), key=swing)
        return {
            "cell": worst["cell"],
            "label": (book.get(worst["cell"]).label if book.get(worst["cell"]) else None),
            "before": worst["before"],
            "after": worst["after"],
            "swing": swing(worst),
            "cells_corrected": len(repaired),
        }
