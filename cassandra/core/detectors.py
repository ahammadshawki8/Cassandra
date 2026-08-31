"""Deterministic detectors: candidate defects, with evidence, and no model calls.

The division of labour in Cassandra is deliberate. These functions locate
candidates and assemble the evidence for each one. They do not decide whether a
candidate is truly a defect, because that requires reading the model's intent,
and they do not propose repairs. That judgement belongs to the agents.

Running detection deterministically means the search is exhaustive, repeatable,
and free. A language model asked to scan a grid for anomalies will miss some,
invent others, and cost a token for every cell it reads. Asked instead to judge
twelve pre-located candidates with their peer context attached, it does the one
part of the job it is actually better at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import networkx as nx

from .model import Workbook, col_to_letters
from .refs import parse_refs
from .regions import Region, region_for
from . import graph as graph_mod

# Constants that are structural rather than assumptions. A model that divides
# by 12 to get a monthly figure is not hiding a driver.
BENIGN_CONSTANTS = {0.0, 1.0, 2.0, 3.0, 4.0, 7.0, 12.0, 24.0, 52.0, 100.0, 365.0, -1.0}

_NUMBER = re.compile(r"(?<![A-Za-z0-9_$:.])(\d+\.?\d*)(?![A-Za-z0-9_(])")

COST_WORDS = (
    "cost", "expense", "opex", "capex", "spend", "churn", "loss", "tax",
    "depreciation", "amortis", "amortiz", "cogs", "outflow", "payment",
)


@dataclass
class Finding:
    """One candidate defect, with everything an agent needs to judge it."""

    cell: str
    detector: str
    defect_class: str
    confidence: float
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)
    blast_radius: list[str] = field(default_factory=list)
    impact: float = 0.0

    def to_prompt(self) -> str:
        """Render the finding as the context an agent reasons over."""
        lines = [
            f"cell: {self.cell}",
            f"suspected: {self.defect_class}",
            f"detector confidence: {self.confidence:.2f}",
            f"observation: {self.summary}",
        ]
        for key, value in self.evidence.items():
            lines.append(f"{key}: {value}")
        if self.blast_radius:
            shown = ", ".join(self.blast_radius[:8])
            more = "" if len(self.blast_radius) <= 8 else f" and {len(self.blast_radius) - 8} more"
            lines.append(f"cells depending on this one: {shown}{more}")
        return "\n".join(lines)


def _value_of(key: str, cell: Any, values: dict[str, Any] | None) -> Any:
    """Computed value if the oracle supplied one, else whatever Excel cached."""
    if values is not None and key in values:
        return values[key]
    return cell.value


def _numeric_literals(formula: str) -> list[float]:
    """Numeric constants in a formula, excluding anything inside a reference."""
    body = formula[1:] if formula.startswith("=") else formula
    spans = [(r.start - 1, r.end - 1) for r in parse_refs(formula)]
    out: list[float] = []
    for match in _NUMBER.finditer(body):
        if any(start <= match.start() < end for start, end in spans):
            continue
        try:
            out.append(float(match.group(1)))
        except ValueError:
            continue
    return out


def detect_hardcodes(book: Workbook, regions: list[Region]) -> list[Finding]:
    """Constants embedded in a formula whose neighbours reference a driver.

    This is the London Whale class. The cell computes the right answer today and
    silently stops tracking its driver forever after.
    """
    findings: list[Finding] = []
    for region in regions:
        for key in region.outliers:
            cell = book.get(key)
            if cell is None or not cell.is_formula:
                continue
            literals = [
                v for v in _numeric_literals(cell.formula or "")
                if v not in BENIGN_CONSTANTS
            ]
            if not literals:
                continue
            boundary = key in region.boundary_outliers
            peers = region.peers(key)
            findings.append(
                Finding(
                    cell=key,
                    detector="hardcode_hunter",
                    defect_class="hardcoded constant replacing a driver reference",
                    confidence=0.45 if boundary else 0.85,
                    summary=(
                        f"formula embeds the literal {literals[0]} while every "
                        f"conforming cell in its region references a driver instead"
                    ),
                    evidence={
                        "formula": cell.formula,
                        "literals": literals,
                        "region": region.describe(),
                        "peer formulas": [book.get(p).formula for p in peers[:3] if book.get(p)],
                        "note": (
                            "boundary cell, may legitimately seed the series"
                            if boundary else "interior cell, hand edited inside a dragged range"
                        ),
                    },
                )
            )
    return findings


def detect_pattern_breaks(book: Workbook, regions: list[Region]) -> list[Finding]:
    """Cells whose R1C1 signature differs from their region, without a literal."""
    findings: list[Finding] = []
    for region in regions:
        for key in region.outliers:
            cell = book.get(key)
            if cell is None or not cell.is_formula:
                continue
            literals = [
                v for v in _numeric_literals(cell.formula or "")
                if v not in BENIGN_CONSTANTS
            ]
            if literals:
                continue  # already reported by the hardcode hunter
            boundary = key in region.boundary_outliers
            findings.append(
                Finding(
                    cell=key,
                    detector="pattern_breaker",
                    defect_class="formula inconsistent with its region",
                    confidence=0.35 if boundary else 0.7,
                    summary=(
                        "this cell computes something structurally different from "
                        "the cells it sits beside"
                    ),
                    evidence={
                        "formula": cell.formula,
                        "its signature": region.signatures.get(key),
                        "region signature": region.majority,
                        "region": region.describe(),
                        "note": (
                            "boundary cell, may legitimately seed the series"
                            if boundary else "interior cell"
                        ),
                    },
                )
            )
    return findings


def detect_range_omissions(
    book: Workbook, dag: nx.DiGraph, values: dict[str, Any] | None = None
) -> list[Finding]:
    """Aggregations that stop short of the data they were meant to cover.

    The signal is structural. A cell sitting immediately past the end of a
    summed range, holding a value of the same kind, that nothing in the workbook
    reads, is almost always a row the aggregation was supposed to include. This
    is the Reinhart and Rogoff class.
    """
    findings: list[Finding] = []
    for key, cell in book.formula_cells.items():
        formula = cell.formula or ""
        if not re.search(r"\b(SUM|AVERAGE|COUNT|MIN|MAX|NPV|SUMPRODUCT)\s*\(", formula, re.I):
            continue

        for ref in parse_refs(formula):
            if not ref.is_range:
                continue
            sheet = ref.sheet or cell.ref.sheet
            row_span = ref.row1 != ref.row2
            col_span = ref.col1 != ref.col2
            if row_span == col_span:
                continue  # only inspect clean one dimensional ranges

            if col_span:
                nxt = f"{sheet}!{col_to_letters(max(ref.col1, ref.col2) + 1)}{ref.row1}"
            else:
                nxt = f"{sheet}!{col_to_letters(ref.col1)}{max(ref.row1, ref.row2) + 1}"

            neighbour = book.get(nxt)
            if neighbour is None:
                continue
            neighbour_value = _value_of(nxt, neighbour, values)
            if not isinstance(neighbour_value, (int, float)) or isinstance(
                neighbour_value, bool
            ):
                continue

            orphaned = nxt in dag and dag.out_degree(nxt) == 0
            findings.append(
                Finding(
                    cell=key,
                    detector="range_auditor",
                    defect_class="aggregation range omits adjacent data",
                    confidence=0.8 if orphaned else 0.45,
                    summary=(
                        f"{formula.strip()} stops at {ref.raw}, but {nxt} holds a "
                        f"value of the same kind"
                        + (" and nothing in the workbook reads it" if orphaned else "")
                    ),
                    evidence={
                        "formula": cell.formula,
                        "range": ref.raw,
                        "first excluded cell": nxt,
                        "its value": neighbour_value,
                        "its formula": neighbour.formula,
                        "read by anything": "no" if orphaned else "yes",
                    },
                )
            )
    return findings


def detect_reference_errors(book: Workbook) -> list[Finding]:
    """Broken references. These are already visibly wrong, but often ignored."""
    findings: list[Finding] = []
    for key, cell in book.formula_cells.items():
        formula = cell.formula or ""
        broken = re.findall(r"#(REF|NAME\?|VALUE!|DIV/0!|N/A|NULL!|NUM!)", formula)
        if not broken and isinstance(cell.value, str) and cell.value.startswith("#"):
            broken = [cell.value]
        if not broken:
            continue
        findings.append(
            Finding(
                cell=key,
                detector="reference_integrity",
                defect_class="broken reference",
                confidence=0.99,
                summary=f"formula contains a broken reference and evaluates to {cell.value}",
                evidence={
                    "formula": cell.formula,
                    "value": cell.value,
                    "note": (
                        "the referenced target no longer exists, so the correct "
                        "repair cannot be inferred from the workbook alone"
                    ),
                },
            )
        )
    return findings


def detect_sign_anomalies(
    book: Workbook, values: dict[str, Any] | None = None
) -> list[Finding]:
    """Cost lines added where they should be subtracted.

    Labels carry the polarity. A term whose label names a cost, entered with a
    plus into a formula that otherwise accumulates, inverts the sign of the
    result. This detector locates the candidate; deciding whether the model's
    convention already stores that line as negative is the agent's job.
    """
    findings: list[Finding] = []
    for key, cell in book.formula_cells.items():
        formula = cell.formula or ""
        refs = parse_refs(formula)
        if len(refs) < 2 or not re.match(r"^=[^,()]*$", formula):
            continue

        for ref in refs:
            if ref.is_range:
                continue
            operand = f"{ref.sheet or cell.ref.sheet}!{col_to_letters(ref.col1)}{ref.row1}"
            operand_cell = book.get(operand)
            if operand_cell is None or not operand_cell.label:
                continue
            label = operand_cell.label.lower()
            if not any(word in label for word in COST_WORDS):
                continue

            preceding = formula[: ref.start].rstrip()
            if not preceding.endswith("+"):
                continue

            value = _value_of(operand, operand_cell, values)
            if isinstance(value, (int, float)) and value < 0:
                continue  # already stored negative, so adding it is correct
            if value is None:
                continue  # polarity unknown, do not guess

            findings.append(
                Finding(
                    cell=key,
                    detector="sign_polarity",
                    defect_class="cost added rather than subtracted",
                    confidence=0.75,
                    summary=(
                        f"{operand} is labelled {operand_cell.label!r} and holds a "
                        f"positive value, but it is added into this formula"
                    ),
                    evidence={
                        "formula": cell.formula,
                        "operand": operand,
                        "operand label": operand_cell.label,
                        "operand value": value,
                        "this cell label": cell.label,
                    },
                )
            )
    return findings


def semantic_candidates(book: Workbook) -> list[Finding]:
    """Labelled formula cells, handed to the Semantic Auditor to read.

    No deterministic rule can tell that a cell labelled Net Margin is computing
    gross margin. This detector only decides which cells are worth a model call:
    those carrying a human label and feeding something downstream.
    """
    findings: list[Finding] = []
    for key, cell in book.formula_cells.items():
        if not cell.label:
            continue
        findings.append(
            Finding(
                cell=key,
                detector="semantic_auditor",
                defect_class="formula may not compute what its label claims",
                confidence=0.0,
                summary="requires reading the label against the formula",
                evidence={
                    "formula": cell.formula,
                    "label": cell.label,
                    "value": cell.value,
                    "number format": cell.number_format,
                },
            )
        )
    return findings


def run_all(
    book: Workbook,
    dag: nx.DiGraph,
    regions: list[Region],
    values: dict[str, Any] | None = None,
) -> list[Finding]:
    """Every deterministic detector, with impact scored over the graph.

    values comes from the calculation oracle. Passing it is strongly preferred:
    a workbook written by anything other than Excel carries no cached values,
    so detectors that reason about magnitude or polarity would otherwise be
    reading None and silently declining to fire.
    """
    findings = (
        detect_hardcodes(book, regions)
        + detect_pattern_breaks(book, regions)
        + detect_range_omissions(book, dag, values)
        + detect_reference_errors(book)
        + detect_sign_anomalies(book, values)
    )
    for finding in findings:
        radius = graph_mod.blast_radius(dag, finding.cell)
        finding.blast_radius = sorted(radius)
        finding.impact = graph_mod.impact_score(dag, book, finding.cell)
    return findings
