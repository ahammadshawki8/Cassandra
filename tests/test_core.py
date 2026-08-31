"""Tests for the deterministic core.

These cover the layer that must never be wrong, because every agent downstream
reasons over its output and the Verifier's authority rests entirely on it.
"""

from __future__ import annotations

import openpyxl
import pytest

from cassandra.core import graph, oracle, parser
from cassandra.core.model import col_to_letters, letters_to_col
from cassandra.core.refs import parse_refs, signature, to_r1c1


@pytest.fixture(scope="module")
def workbook_path(tmp_path_factory):
    """A tiny model carrying a planted range defect: the SUM omits its last row."""
    path = tmp_path_factory.mktemp("wb") / "model.xlsx"
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Model"
    sheet["A1"] = "Revenue"
    for i, value in enumerate([10, 20, 30, 40], start=2):
        sheet.cell(row=i, column=1, value=value)
    sheet["A6"] = "Total"
    sheet["B6"] = "=SUM(A2:A4)"
    sheet["A7"] = "With uplift"
    sheet["B7"] = "=B6*1.15"
    book.save(path)
    return str(path)


class TestColumnConversion:
    @pytest.mark.parametrize(
        "index,letters", [(1, "A"), (26, "Z"), (27, "AA"), (52, "AZ"), (702, "ZZ")]
    )
    def test_roundtrip(self, index, letters):
        assert col_to_letters(index) == letters
        assert letters_to_col(letters) == index

    def test_rejects_zero(self):
        with pytest.raises(ValueError):
            col_to_letters(0)


class TestReferenceParsing:
    def test_function_name_is_not_a_reference(self):
        """LOG10( must not parse as column LOG row 10."""
        assert to_r1c1("=LOG10(A1)", 5, 1) == "=LOG10(R[-4]C)"

    def test_string_literal_contents_are_ignored(self):
        assert "Q1:Z9" in to_r1c1('=IF(A1>0,"Q1:Z9",B2)', 3, 3)

    def test_quoted_sheet_name_survives(self):
        assert to_r1c1("='P L'!A1", 3, 2) == "='P L'!R[-2]C[-1]"

    def test_absolute_reference_stays_absolute(self):
        assert to_r1c1("=$A$1*B2", 4, 2) == "=R1C1*R[-2]C"

    def test_range_cell_count(self):
        refs = parse_refs("=SUM(A2:A4)+B1")
        assert [r.cell_count for r in refs] == [3, 1]

    def test_range_expands_to_keys(self):
        (ref,) = parse_refs("=SUM(A2:A4)")
        assert ref.cells("Model") == ["Model!A2", "Model!A3", "Model!A4"]


class TestSignature:
    def test_same_intent_different_columns_share_a_signature(self):
        """This is the premise the Pattern Breaker agent depends on."""
        assert signature("=SUM(A2:A4)", 6, 2) == signature("=SUM(B2:B4)", 6, 3)

    def test_hardcoded_constant_breaks_the_signature(self):
        assert signature("=SUM(A2:A4)", 6, 2) != signature("=SUM(A2:A4)*1.15", 6, 2)

    def test_shifted_range_breaks_the_signature(self):
        assert signature("=SUM(A2:A4)", 6, 2) != signature("=SUM(A2:A5)", 6, 2)


class TestParser:
    def test_extracts_formulas_and_values(self, workbook_path):
        book = parser.parse(workbook_path)
        assert set(book.formula_cells) == {"Model!B6", "Model!B7"}
        assert book.get("Model!A2").value == 10

    def test_attaches_row_labels(self, workbook_path):
        book = parser.parse(workbook_path)
        assert "Total" in (book.get("Model!B6").label or "")


class TestGraph:
    def test_edges_follow_data_flow(self, workbook_path):
        book = parser.parse(workbook_path)
        dag = graph.build(book)
        assert graph.blast_radius(dag, "Model!A3") == {"Model!B6", "Model!B7"}

    def test_omitted_cell_has_no_dependents(self, workbook_path):
        """A5 is excluded by the defect, so nothing reads it. That is the signal."""
        book = parser.parse(workbook_path)
        dag = graph.build(book)
        assert graph.blast_radius(dag, "Model!A5") == set()

    def test_terminal_formula_is_an_output(self, workbook_path):
        book = parser.parse(workbook_path)
        dag = graph.build(book)
        assert graph.output_cells(dag, book) == ["Model!B7"]

    def test_impact_weights_reaching_an_output(self, workbook_path):
        book = parser.parse(workbook_path)
        dag = graph.build(book)
        assert graph.impact_score(dag, book, "Model!A3") > graph.impact_score(
            dag, book, "Model!B7"
        )


class TestOracleEquality:
    def test_floating_point_noise_is_not_a_change(self):
        assert oracle.equal(115.0, 114.99999999999999)

    def test_real_movement_is_a_change(self):
        assert not oracle.equal(100.0, 115.0)

    def test_zero_and_tiny_are_distinguished_by_absolute_floor(self):
        assert oracle.equal(0.0, 1e-12)
        assert not oracle.equal(0.0, 1e-3)


class TestVerifier:
    """The Verifier is the system's authority. Each failure mode must be caught."""

    @pytest.fixture(scope="class")
    def context(self, workbook_path):
        book = parser.parse(workbook_path)
        dag = graph.build(book)
        names = list(book.sheets)
        base = oracle.calculate(workbook_path, names)
        radius = graph.blast_radius(dag, "Model!B6")
        return workbook_path, names, base, radius

    def test_baseline_reflects_the_defect(self, context):
        _, _, base, _ = context
        assert base.get("Model!B6") == 60.0

    def test_accepts_a_correct_patch(self, context):
        path, names, base, radius = context
        verdict = oracle.verify(
            path, "Model!B6", "=SUM(A2:A5)", 100.0, radius, base, names
        )
        assert verdict.passed
        assert {d.key for d in verdict.intended_deltas} == {"Model!B6", "Model!B7"}

    def test_rejects_a_hallucinated_prediction(self, context):
        """The patch is right but the agent's claim about it is wrong."""
        path, names, base, radius = context
        verdict = oracle.verify(
            path, "Model!B6", "=SUM(A2:A5)", 999.0, radius, base, names
        )
        assert not verdict.passed
        assert "999.0" in verdict.reason

    def test_rejects_a_no_op_patch(self, context):
        path, names, base, radius = context
        verdict = oracle.verify(
            path, "Model!B6", "=SUM(A2:A4)", 100.0, radius, base, names
        )
        assert not verdict.passed
        assert "changed nothing" in verdict.reason

    def test_rejects_a_patch_producing_an_excel_error(self, context):
        path, names, base, radius = context
        verdict = oracle.verify(
            path, "Model!B6", "=SUM(A2:A5)/0", 100.0, radius, base, names
        )
        assert not verdict.passed
        assert "#DIV/0!" in verdict.reason

    def test_original_workbook_is_never_mutated(self, context):
        path, names, base, radius = context
        oracle.verify(path, "Model!B6", "=SUM(A2:A5)", 100.0, radius, base, names)
        assert oracle.calculate(path, names).get("Model!B6") == 60.0
