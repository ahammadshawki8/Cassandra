"""Tests for the ways a workbook gets in, and the corrected file that comes out.

These exercise the real code paths. The only thing stubbed is the network call
to Google, because a live test would depend on a third party sheet staying
shared, which is not a property a test suite should rely on. Everything either
side of that call is the code that runs in production.
"""

from __future__ import annotations

import openpyxl
import pytest

from cassandra.core import oracle, parser
from cassandra.service import sources


@pytest.fixture(scope="module")
def workbook_bytes(tmp_path_factory) -> bytes:
    path = tmp_path_factory.mktemp("src") / "model.xlsx"
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Model"
    for i, v in enumerate([10, 20, 30, 40], start=2):
        sheet.cell(row=i, column=1, value=v)
    sheet["A6"] = "Total"
    sheet["B6"] = "=SUM(A2:A4)"
    book.save(path)
    return path.read_bytes()


class TestRejections:
    """Every refusal has to tell the person what to do instead."""

    def test_csv_is_refused_with_the_reason(self):
        with pytest.raises(sources.SourceError) as e:
            sources.from_upload("data.csv", b"a,b\n1,2\n")
        assert "no formulas" in str(e.value)
        assert ".xlsx" in str(e.value)

    def test_legacy_formats_name_the_fix(self):
        with pytest.raises(sources.SourceError) as e:
            sources.from_upload("old.xls", b"whatever")
        assert ".xlsx" in str(e.value)

    def test_unknown_extension(self):
        with pytest.raises(sources.SourceError):
            sources.from_upload("notes.txt", b"hello")

    def test_a_renamed_file_is_caught_by_its_bytes(self):
        """An .xlsx is a zip. A file renamed rather than saved is not one."""
        with pytest.raises(sources.SourceError) as e:
            sources.from_upload("fake.xlsx", b"this is plain text")
        assert "renamed" in str(e.value)

    def test_empty_upload(self):
        with pytest.raises(sources.SourceError):
            sources.from_upload("empty.xlsx", b"")

    def test_oversized_upload(self):
        with pytest.raises(sources.SourceError) as e:
            sources.from_upload("big.xlsx", b"PK" + b"0" * (sources.MAX_BYTES + 1))
        assert "larger than" in str(e.value)


class TestUpload:
    def test_a_real_workbook_lands_on_disk_and_parses(self, workbook_bytes):
        src = sources.from_upload("quarterly model.xlsx", workbook_bytes)
        assert src.origin == "upload"
        book = parser.parse(src.path)
        assert book.get("Model!B6").formula == "=SUM(A2:A4)"

    def test_path_separators_cannot_escape_the_work_directory(self, workbook_bytes):
        src = sources.from_upload("../../etc/passwd.xlsx", workbook_bytes)
        assert ".." not in src.name and "/" not in src.name


class TestGoogleSheets:
    """The import path, with only the call to Google replaced."""

    URL = "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit#gid=0"

    def test_a_link_that_is_not_sheets_is_rejected(self):
        with pytest.raises(sources.SourceError) as e:
            sources.from_google_sheet("https://example.com/thing")
        assert "not a Google Sheets link" in str(e.value)

    def test_the_export_url_is_built_from_the_sheet_id(self, monkeypatch, workbook_bytes):
        seen = {}

        class Reply:
            status_code = 200
            content = workbook_bytes

        def fake_get(url, **kwargs):
            seen["url"] = url
            return Reply()

        monkeypatch.setattr(sources.requests, "get", fake_get)
        src = sources.from_google_sheet(self.URL)

        assert "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789" in seen["url"]
        assert seen["url"].endswith("/export?format=xlsx")
        assert src.origin == "google_sheets"

    def test_an_imported_sheet_is_a_workbook_the_auditor_can_read(
        self, monkeypatch, workbook_bytes
    ):
        """The whole point: what comes back is auditable, not just downloaded."""

        class Reply:
            status_code = 200
            content = workbook_bytes

        monkeypatch.setattr(sources.requests, "get", lambda url, **kw: Reply())
        src = sources.from_google_sheet(self.URL)

        book = parser.parse(src.path)
        assert book.get("Model!B6").formula == "=SUM(A2:A4)"
        assert oracle.calculate(src.path, list(book.sheets)).get("Model!B6") == 60.0

    def test_a_private_sheet_explains_how_to_share_it(self, monkeypatch):
        class Reply:
            status_code = 200
            content = b"<html><head><title>Sign in</title></head>"

        monkeypatch.setattr(sources.requests, "get", lambda url, **kw: Reply())
        with pytest.raises(sources.SourceError) as e:
            sources.from_google_sheet(self.URL)
        assert "Anyone with the link" in str(e.value)

    def test_a_forbidden_response_explains_how_to_share_it(self, monkeypatch):
        class Reply:
            status_code = 403
            content = b""

        monkeypatch.setattr(sources.requests, "get", lambda url, **kw: Reply())
        with pytest.raises(sources.SourceError) as e:
            sources.from_google_sheet(self.URL)
        assert "private" in str(e.value)

    def test_a_network_failure_is_reported_not_swallowed(self, monkeypatch):
        def boom(url, **kw):
            raise sources.requests.RequestException("connection reset")

        monkeypatch.setattr(sources.requests, "get", boom)
        with pytest.raises(sources.SourceError) as e:
            sources.from_google_sheet(self.URL)
        assert "connection reset" in str(e.value)


class TestCorrectedCopy:
    """The artifact that makes this a tool rather than a report."""

    def test_corrections_are_written_and_the_original_is_untouched(self, workbook_bytes):
        src = sources.from_upload("model.xlsx", workbook_bytes)
        before = oracle.calculate(src.path, ["Model"]).get("Model!B6")
        assert before == 60.0

        out = sources.corrected_copy(src.path, {"Model!B6": "=SUM(A2:A5)"})
        assert out != src.path

        fixed = parser.parse(out)
        assert fixed.get("Model!B6").formula == "=SUM(A2:A5)"
        assert oracle.calculate(out, ["Model"]).get("Model!B6") == 100.0

        # The file the user uploaded must be exactly as they left it.
        assert oracle.calculate(src.path, ["Model"]).get("Model!B6") == 60.0

    def test_a_missing_original_says_so_rather_than_failing_obscurely(self):
        with pytest.raises(sources.SourceError) as e:
            sources.corrected_copy("no/such/file.xlsx", {"Model!B6": "=1"})
        assert "Run the audit again" in str(e.value)


class TestPathLeaf:
    """Run titles come from paths recorded on whichever machine ran the audit."""

    def test_a_windows_path_is_reduced_on_a_linux_container(self):
        from cassandra.service.app import _leaf

        # os.path.basename only splits on the host separator, so this exact case
        # once put an entire temporary path in the history rail.
        assert _leaf(r"C:\Users\a\AppData\Local\Temp\cassandra\model.xlsx") == "model.xlsx"

    def test_posix_and_bare_names(self):
        from cassandra.service.app import _leaf

        assert _leaf("/tmp/cassandra/model.xlsx") == "model.xlsx"
        assert _leaf("demo/model.xlsx") == "model.xlsx"
        assert _leaf("model.xlsx") == "model.xlsx"

    def test_missing_path_is_empty_not_an_error(self):
        from cassandra.service.app import _leaf

        assert _leaf(None) == ""
