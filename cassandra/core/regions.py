"""Region clustering: grouping cells that were meant to do the same thing.

Financial models are built by writing one formula and dragging it across a row
or down a column. Every cell in that stretch shares a single intent, so under
R1C1 normalization they collapse to a single signature. A cell whose signature
differs from the rest of its stretch was edited by hand, and hand edits inside
a dragged range are where defects live.

This is the mechanism CUSTODES established (Kim et al., ICSE 2016): smelly
cells are outliers within clusters formed by tabulation style. The clustering
here is deliberately conservative. A region must be long enough for a majority
to mean something, and the outlier must be a genuine minority, because flagging
a two cell row where the cells simply differ produces noise rather than signal.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .model import Workbook
from .refs import signature

# A stretch shorter than this cannot establish a norm worth trusting.
MIN_REGION = 3

# An outlier must be a real minority. At or above this share it is not an
# outlier, it is a disagreement, and the region is simply not homogeneous.
MAX_OUTLIER_SHARE = 0.4


@dataclass
class Region:
    """A run of adjacent formula cells that should share one intent."""

    sheet: str
    orientation: str
    cells: list[str] = field(default_factory=list)
    signatures: dict[str, str] = field(default_factory=dict)
    majority: str = ""
    outliers: list[str] = field(default_factory=list)
    boundary_outliers: list[str] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.cells)

    @property
    def interior_outliers(self) -> list[str]:
        """Outliers that are not explainable as a series seed or terminator."""
        return [c for c in self.outliers if c not in self.boundary_outliers]

    @property
    def is_homogeneous(self) -> bool:
        return not self.outliers

    def peers(self, key: str) -> list[str]:
        """The conforming cells a suspect should be compared against."""
        return [c for c in self.cells if c not in self.outliers and c != key]

    def describe(self) -> str:
        span = f"{self.cells[0]} through {self.cells[-1].split('!')[-1]}"
        return f"{self.orientation} region {span} ({self.size} cells)"


def _runs(indices: list[int]) -> list[list[int]]:
    """Split sorted indices into runs of consecutive positions."""
    if not indices:
        return []
    out: list[list[int]] = [[indices[0]]]
    for i in indices[1:]:
        if i == out[-1][-1] + 1:
            out[-1].append(i)
        else:
            out.append([i])
    return out


def _classify(region: Region) -> Region:
    """Establish the region's majority signature and mark its outliers."""
    counts = Counter(region.signatures.values())
    if not counts:
        return region
    majority, majority_count = counts.most_common(1)[0]
    region.majority = majority

    minority = region.size - majority_count
    if majority_count <= 1 or minority / region.size > MAX_OUTLIER_SHARE:
        # No credible norm, so nothing here is an outlier.
        return region

    region.outliers = [
        key for key, sig in region.signatures.items() if sig != majority
    ]

    # The first cell of a series is routinely a legitimate seed: a row of
    # compounding quarters begins by reading an assumption rather than the
    # quarter before it, so it cannot match its own successors. The last cell is
    # occasionally a terminator for the same reason. Flagging these as defects
    # is the most common false positive in signature clustering, so they are
    # separated out and carry lower confidence downstream rather than being
    # discarded, because a boundary cell can still be genuinely wrong.
    ends = {region.cells[0], region.cells[-1]}
    region.boundary_outliers = [key for key in region.outliers if key in ends]
    return region


def cluster(book: Workbook) -> list[Region]:
    """Find every homogeneous run of formula cells, and its outliers."""
    regions: list[Region] = []

    for sheet in book.sheets.values():
        formulas = {
            key: cell for key, cell in sheet.cells.items() if cell.is_formula
        }
        if not formulas:
            continue

        by_row: dict[int, list[int]] = {}
        by_col: dict[int, list[int]] = {}
        for cell in formulas.values():
            by_row.setdefault(cell.ref.row, []).append(cell.ref.col)
            by_col.setdefault(cell.ref.col, []).append(cell.ref.row)

        for row, cols in by_row.items():
            for run in _runs(sorted(cols)):
                if len(run) < MIN_REGION:
                    continue
                region = Region(sheet=sheet.name, orientation="row")
                for col in run:
                    cell = sheet.get(row, col)
                    if cell is None:
                        continue
                    region.cells.append(cell.key)
                    region.signatures[cell.key] = signature(
                        cell.formula or "", cell.ref.row, cell.ref.col
                    )
                regions.append(_classify(region))

        for col, rows in by_col.items():
            for run in _runs(sorted(rows)):
                if len(run) < MIN_REGION:
                    continue
                region = Region(sheet=sheet.name, orientation="column")
                for row in run:
                    cell = sheet.get(row, col)
                    if cell is None:
                        continue
                    region.cells.append(cell.key)
                    region.signatures[cell.key] = signature(
                        cell.formula or "", cell.ref.row, cell.ref.col
                    )
                regions.append(_classify(region))

    return regions


def region_for(regions: list[Region], key: str) -> Region | None:
    """The largest region containing this cell, which is its strongest context."""
    holding = [r for r in regions if key in r.cells]
    return max(holding, key=lambda r: r.size) if holding else None
