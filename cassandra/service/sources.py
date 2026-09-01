"""Getting a workbook in, from wherever it lives.

Three ways in, and one way out.

  a file dropped on the page
  a Google Sheets link
  an object landing in the bucket

The output is always a path to a local .xlsx, because everything downstream
reasons over a real workbook with real formulas.

A note on CSV, which people reasonably ask for: a CSV holds values and no
formulas. There is nothing in it to audit, because the defects Cassandra finds
are defects in how a number was computed, and a CSV has already thrown that
away. Files are rejected with that explanation rather than accepted and then
silently found to be clean.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass

import requests

SHEET_ID = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]{20,})")
WORKBOOK_SUFFIXES = (".xlsx", ".xlsm")

MAX_BYTES = 25 * 1024 * 1024


class SourceError(Exception):
    """Something the user needs to know about and can act on."""


@dataclass
class Source:
    path: str
    name: str
    origin: str


def _workdir() -> str:
    d = os.environ.get("CASSANDRA_WORKDIR", os.path.join(tempfile.gettempdir(), "cassandra"))
    os.makedirs(d, exist_ok=True)
    return d


def _check_name(name: str) -> None:
    lower = name.lower()
    if lower.endswith(".csv"):
        raise SourceError(
            "A CSV holds values but no formulas, and Cassandra audits how numbers "
            "are computed. Export the sheet as .xlsx and the formulas come with it."
        )
    if lower.endswith((".xls", ".numbers", ".ods")):
        raise SourceError(
            f"{os.path.splitext(name)[1]} is not readable here. Save the file as "
            ".xlsx, which keeps every formula."
        )
    if not lower.endswith(WORKBOOK_SUFFIXES):
        raise SourceError("Upload an .xlsx or .xlsm workbook.")


def from_upload(name: str, blob: bytes) -> Source:
    """A workbook uploaded through the page."""
    _check_name(name)
    if not blob:
        raise SourceError("That file is empty.")
    if len(blob) > MAX_BYTES:
        raise SourceError(f"That file is larger than {MAX_BYTES // (1024 * 1024)}MB.")
    if not blob.startswith(b"PK"):
        raise SourceError(
            "That does not look like a workbook. An .xlsx is a zip archive and "
            "this file is not one, so it may have been renamed rather than saved."
        )

    safe = os.path.basename(name).replace("\\", "_").replace("/", "_")
    path = os.path.join(_workdir(), safe)
    with open(path, "wb") as handle:
        handle.write(blob)
    return Source(path=path, name=safe, origin="upload")


def from_google_sheet(url: str) -> Source:
    """A Google Sheet, exported through the endpoint Sheets already provides.

    This deliberately avoids OAuth. Any sheet shared as "anyone with the link"
    exports directly, which covers the models people actually circulate, and it
    means nobody has to grant an app access to their whole Drive to audit one
    file.
    """
    match = SHEET_ID.search(url or "")
    if not match:
        raise SourceError(
            "That is not a Google Sheets link. It should look like "
            "docs.google.com/spreadsheets/d/..."
        )
    sheet_id = match.group(1)
    export = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"

    try:
        response = requests.get(export, timeout=45, allow_redirects=True)
    except requests.RequestException as exc:
        raise SourceError(f"Could not reach Google Sheets: {exc}") from exc

    if response.status_code in (401, 403) or b"<html" in response.content[:400].lower():
        raise SourceError(
            "That sheet is private. Open Share, set General access to "
            "\"Anyone with the link\", and paste the link again. Viewer is enough."
        )
    if response.status_code != 200:
        raise SourceError(f"Google Sheets returned {response.status_code} for that link.")
    if not response.content.startswith(b"PK"):
        raise SourceError("Google Sheets did not return a workbook for that link.")

    name = f"sheet_{sheet_id[:10]}.xlsx"
    path = os.path.join(_workdir(), name)
    with open(path, "wb") as handle:
        handle.write(response.content)
    return Source(path=path, name=name, origin="google_sheets")


def from_bucket(bucket: str, blob_name: str) -> Source:
    """An object that landed in the watched bucket."""
    _check_name(blob_name)
    from google.cloud import storage

    path = os.path.join(_workdir(), os.path.basename(blob_name))
    storage.Client().bucket(bucket).blob(blob_name).download_to_filename(path)
    return Source(path=path, name=os.path.basename(blob_name), origin=f"gs://{bucket}")


# Archived sources live under this prefix. The push endpoint skips it, because
# the bucket that receives workbooks is the same one that keeps them and an
# archive write would otherwise fire OBJECT_FINALIZE and audit itself forever.
RUN_PREFIX = "runs"


def archive_key(run_id: str, workbook_path: str) -> str:
    """Where a run's source workbook is kept so it outlives the container."""
    name = re.split(r"[\\/]", workbook_path or "")[-1] or "workbook.xlsx"
    return f"{RUN_PREFIX}/{run_id}/{name}"


def archive(bucket: str, run_id: str, source_path: str) -> None:
    """Keep the source workbook so a corrected copy can be rebuilt later.

    Cloud Run scales to zero, so the local file a run was audited from is gone
    the moment the instance recycles. Without this, every stored run's corrected
    download stops working as soon as the service goes idle, which is the normal
    case rather than an edge one.
    """
    if not bucket or not os.path.exists(source_path):
        return
    from google.cloud import storage

    storage.Client().bucket(bucket).blob(
        archive_key(run_id, source_path)
    ).upload_from_filename(source_path)


def restore(bucket: str, run_id: str, workbook_path: str) -> str:
    """Fetch a run's archived source workbook back onto local disk."""
    if not bucket:
        raise SourceError(
            "The original workbook is no longer on this instance and no archive "
            "bucket is configured, so a corrected copy cannot be rebuilt."
        )
    from google.cloud import storage

    key = archive_key(run_id, workbook_path)
    dest = os.path.join(_workdir(), f"{run_id}.{key.rsplit('/', 1)[-1]}")
    blob = storage.Client().bucket(bucket).blob(key)
    if not blob.exists():
        raise SourceError(
            "The original workbook for this run was not archived, so a corrected "
            "copy cannot be rebuilt. Run the audit again to download one."
        )
    blob.download_to_filename(dest)
    return dest


def corrected_copy(source_path: str, patches: dict[str, str]) -> str:
    """Write a copy of the workbook with every verified correction applied.

    The original is never touched. This is the artifact that makes Cassandra a
    tool rather than a report: the file you can open, check, and keep.
    """
    if not os.path.exists(source_path):
        raise SourceError(
            "The original workbook is no longer on this instance, so a corrected "
            "copy cannot be built. Run the audit again to download one."
        )
    from ..core import oracle

    stem, ext = os.path.splitext(os.path.basename(source_path))
    dest = os.path.join(_workdir(), f"{stem}.corrected{ext}")
    return oracle.apply_patch(source_path, patches, dest)
