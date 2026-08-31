"""Core data model for a parsed workbook.

Everything in this module is deterministic. No language model is involved at
this layer, by design: a parser establishes ground truth about a workbook far
more reliably than a model can, and the agents downstream reason over this
structure rather than over raw grid text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CellRef:
    """A fully qualified reference to a single cell."""

    sheet: str
    row: int
    col: int

    @property
    def a1(self) -> str:
        return f"{col_to_letters(self.col)}{self.row}"

    @property
    def key(self) -> str:
        return f"{self.sheet}!{self.a1}"

    def __str__(self) -> str:
        return self.key


@dataclass
class Cell:
    """A single cell, its literal content, and its computed value."""

    ref: CellRef
    formula: str | None = None
    value: Any = None
    label: str | None = None
    number_format: str | None = None

    @property
    def is_formula(self) -> bool:
        return self.formula is not None

    @property
    def key(self) -> str:
        return self.ref.key


@dataclass
class Sheet:
    name: str
    cells: dict[str, Cell] = field(default_factory=dict)
    max_row: int = 0
    max_col: int = 0

    def get(self, row: int, col: int) -> Cell | None:
        return self.cells.get(f"{self.name}!{col_to_letters(col)}{row}")


@dataclass
class Workbook:
    """A parsed workbook. Keyed by "Sheet!A1" throughout the system."""

    path: str
    sheets: dict[str, Sheet] = field(default_factory=dict)

    @property
    def cells(self) -> dict[str, Cell]:
        out: dict[str, Cell] = {}
        for sheet in self.sheets.values():
            out.update(sheet.cells)
        return out

    @property
    def formula_cells(self) -> dict[str, Cell]:
        return {k: c for k, c in self.cells.items() if c.is_formula}

    def get(self, key: str) -> Cell | None:
        return self.cells.get(key)


def col_to_letters(col: int) -> str:
    """1 -> A, 26 -> Z, 27 -> AA."""
    if col < 1:
        raise ValueError(f"column index must be positive, got {col}")
    letters = ""
    while col > 0:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def letters_to_col(letters: str) -> int:
    """A -> 1, Z -> 26, AA -> 27."""
    col = 0
    for ch in letters.upper():
        if not ch.isalpha():
            raise ValueError(f"invalid column letters: {letters}")
        col = col * 26 + (ord(ch) - 64)
    return col
