"""Formula reference parsing and R1C1 normalization.

The R1C1 normalization is the load bearing idea behind the Pattern Breaker
agent. Two cells that implement the same intent in adjacent columns have
different A1 formulas but identical R1C1 signatures. A cell whose signature
differs from the rest of its region is, per CUSTODES (ICSE 2016), an outlier
worth suspecting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .model import col_to_letters, letters_to_col

# A reference, optionally sheet qualified, optionally a range.
# The trailing negative lookahead rejects function names such as LOG10(, which
# would otherwise parse as column "LOG" row 10.
_REF = re.compile(
    r"(?:(?:'(?P<qsheet>[^']+)'|(?P<sheet>[A-Za-z_][A-Za-z0-9_.]*))!)?"
    r"(?P<c1>\$?[A-Za-z]{1,3})(?P<r1>\$?\d+)(?!\d)"
    r"(?::(?P<c2>\$?[A-Za-z]{1,3})(?P<r2>\$?\d+)(?!\d))?"
    r"(?![\d(])(?!\s*\()"
)

# String literals inside a formula must never be scanned for references.
_STRING = re.compile(r'"[^"]*"')


@dataclass(frozen=True)
class ParsedRef:
    """One reference occurrence inside a formula."""

    sheet: str | None
    col1: int
    row1: int
    col2: int | None
    row2: int | None
    col1_abs: bool
    row1_abs: bool
    col2_abs: bool
    row2_abs: bool
    start: int
    end: int
    raw: str

    @property
    def is_range(self) -> bool:
        return self.col2 is not None

    def cells(self, sheet_default: str) -> list[str]:
        """Expand to the list of "Sheet!A1" keys this reference covers."""
        sheet = self.sheet or sheet_default
        c2 = self.col2 if self.col2 is not None else self.col1
        r2 = self.row2 if self.row2 is not None else self.row1
        lo_c, hi_c = min(self.col1, c2), max(self.col1, c2)
        lo_r, hi_r = min(self.row1, r2), max(self.row1, r2)
        return [
            f"{sheet}!{col_to_letters(c)}{r}"
            for c in range(lo_c, hi_c + 1)
            for r in range(lo_r, hi_r + 1)
        ]

    @property
    def cell_count(self) -> int:
        c2 = self.col2 if self.col2 is not None else self.col1
        r2 = self.row2 if self.row2 is not None else self.row1
        return (abs(self.col1 - c2) + 1) * (abs(self.row1 - r2) + 1)


def _mask_strings(formula: str) -> str:
    """Replace string literal contents with filler so refs inside are not parsed."""
    return _STRING.sub(lambda m: '"' + "\x00" * (len(m.group(0)) - 2) + '"', formula)


def parse_refs(formula: str) -> list[ParsedRef]:
    """Extract every cell or range reference from a formula."""
    if not formula:
        return []
    body = formula[1:] if formula.startswith("=") else formula
    offset = 1 if formula.startswith("=") else 0
    masked = _mask_strings(body)

    refs: list[ParsedRef] = []
    for m in _REF.finditer(masked):
        c1_raw, r1_raw = m.group("c1"), m.group("r1")
        c2_raw, r2_raw = m.group("c2"), m.group("r2")
        try:
            col1 = letters_to_col(c1_raw.lstrip("$"))
            row1 = int(r1_raw.lstrip("$"))
        except ValueError:
            continue
        col2 = letters_to_col(c2_raw.lstrip("$")) if c2_raw else None
        row2 = int(r2_raw.lstrip("$")) if r2_raw else None
        refs.append(
            ParsedRef(
                sheet=m.group("qsheet") or m.group("sheet"),
                col1=col1,
                row1=row1,
                col2=col2,
                row2=row2,
                col1_abs=c1_raw.startswith("$"),
                row1_abs=r1_raw.startswith("$"),
                col2_abs=bool(c2_raw and c2_raw.startswith("$")),
                row2_abs=bool(r2_raw and r2_raw.startswith("$")),
                start=m.start() + offset,
                end=m.end() + offset,
                raw=m.group(0),
            )
        )
    return refs


_BARE_SHEET = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


def _quote_sheet(name: str) -> str:
    """Re-quote a sheet name that cannot be written bare."""
    return name if _BARE_SHEET.match(name) else f"'{name}'"


def _r1c1_part(value: int, anchor: int, is_abs: bool, letter: str) -> str:
    if is_abs:
        return f"{letter}{value}"
    delta = value - anchor
    return f"{letter}[{delta}]" if delta else f"{letter}"


def to_r1c1(formula: str, row: int, col: int) -> str:
    """Rewrite a formula into R1C1 form relative to the cell that holds it.

    =SUM(A2:A4) at B6 and =SUM(B2:B4) at C6 both become =SUM(R[-4]C[-1]:R[-2]C[-1]),
    so a region of cells implementing one intent collapses to one signature.
    """
    if not formula:
        return ""
    refs = parse_refs(formula)
    if not refs:
        return formula

    out: list[str] = []
    cursor = 0
    for ref in refs:
        out.append(formula[cursor : ref.start])
        sheet_prefix = f"{_quote_sheet(ref.sheet)}!" if ref.sheet else ""
        first = (
            _r1c1_part(ref.row1, row, ref.row1_abs, "R")
            + _r1c1_part(ref.col1, col, ref.col1_abs, "C")
        )
        if ref.is_range:
            second = (
                _r1c1_part(ref.row2, row, ref.row2_abs, "R")
                + _r1c1_part(ref.col2, col, ref.col2_abs, "C")
            )
            out.append(f"{sheet_prefix}{first}:{second}")
        else:
            out.append(f"{sheet_prefix}{first}")
        cursor = ref.end
    out.append(formula[cursor:])
    return "".join(out)


def signature(formula: str, row: int, col: int) -> str:
    """Normalized R1C1 signature used to cluster cells into regions."""
    return re.sub(r"\s+", "", to_r1c1(formula, row, col)).upper()
