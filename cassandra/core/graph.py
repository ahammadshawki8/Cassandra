"""The formula dependency graph, and blast radius over it.

Blast radius is the reason Cassandra can rank findings by consequence rather
than by rule violation. A defect in a cell that nothing depends on is a typo.
The same defect in a cell that feeds the headline figure is an incident.
"""

from __future__ import annotations

import networkx as nx

from .model import Workbook
from .refs import parse_refs


def build(book: Workbook) -> nx.DiGraph:
    """Build the precedent to dependent graph over every cell in the workbook.

    An edge A -> B means "B reads A", so a change at A propagates to B.
    """
    g = nx.DiGraph()
    for key in book.cells:
        g.add_node(key)

    for key, cell in book.formula_cells.items():
        for ref in parse_refs(cell.formula or ""):
            for precedent in ref.cells(cell.ref.sheet):
                if precedent == key:
                    continue
                if precedent not in g:
                    g.add_node(precedent)
                g.add_edge(precedent, key)
    return g


def blast_radius(g: nx.DiGraph, key: str) -> set[str]:
    """Every cell whose value can change if this cell changes."""
    if key not in g:
        return set()
    return nx.descendants(g, key)


def precedents(g: nx.DiGraph, key: str, depth: int = 1) -> set[str]:
    """Cells this cell reads, directly or transitively."""
    if key not in g:
        return set()
    if depth == 1:
        return set(g.predecessors(key))
    return nx.ancestors(g, key)


def output_cells(g: nx.DiGraph, book: Workbook) -> list[str]:
    """Formula cells nothing else depends on: the figures a human actually reads."""
    return [k for k in book.formula_cells if g.out_degree(k) == 0]


def find_cycles(g: nx.DiGraph) -> list[list[str]]:
    """Circular references. Excel tolerates these; correctness does not."""
    try:
        return [c for c in nx.simple_cycles(g)]
    except Exception:
        return []


def impact_score(g: nx.DiGraph, book: Workbook, key: str) -> float:
    """Rank a cell by consequence: how far a change reaches, weighted toward outputs.

    Reaching a terminal output figure matters more than reaching an intermediate,
    because outputs are what a human quotes in a board meeting.
    """
    radius = blast_radius(g, key)
    if not radius:
        return 0.0
    outputs = set(output_cells(g, book))
    return float(len(radius)) + 4.0 * float(len(radius & outputs))
