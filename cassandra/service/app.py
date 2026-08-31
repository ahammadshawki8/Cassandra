"""The Cloud Run service: Pub/Sub push endpoint, live trace stream, dashboard.

One container serves three jobs. It receives the Pub/Sub push that fires when a
workbook lands in the bucket, runs the audit, and serves the dashboard that
watches it happen.

The audit runs on a worker thread and publishes events to an in process bus, so
the push request returns immediately. Pub/Sub retries anything it does not get
an acknowledgement for within its deadline, and an audit takes minutes, so
holding the request open would guarantee duplicate deliveries.
"""

from __future__ import annotations

import base64
import json
import os
import queue
import threading
import time
from typing import Any

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import (
    FileResponse, HTMLResponse, JSONResponse, StreamingResponse,
)

from ..orchestrator import Auditor
from . import sources
from .store import Store

HERE = os.path.dirname(__file__)
WORKDIR = os.environ.get("CASSANDRA_WORKDIR", "/tmp/cassandra")
BUCKET = os.environ.get("CASSANDRA_BUCKET", "")

app = FastAPI(title="Cassandra", docs_url="/api/docs")
store = Store()


class Bus:
    """Fan out of audit events to every connected dashboard."""

    def __init__(self) -> None:
        self._subscribers: list[queue.Queue] = []
        self._history: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def publish(self, event: dict[str, Any]) -> None:
        with self._lock:
            self._history.append(event)
            self._history = self._history[-500:]
            targets = list(self._subscribers)
        for q in targets:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=1000)
        with self._lock:
            for event in self._history[-80:]:
                q.put_nowait(event)
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)


bus = Bus()
_running = threading.Lock()


def _download(bucket: str, name: str) -> str:
    from google.cloud import storage

    os.makedirs(WORKDIR, exist_ok=True)
    local = os.path.join(WORKDIR, os.path.basename(name))
    storage.Client().bucket(bucket).blob(name).download_to_filename(local)
    return local


_sources: dict[str, str] = {}


def _audit(path: str, source: str, label: str = "") -> None:
    """Run one audit, publishing events as it goes, and persist the result."""
    if not _running.acquire(blocking=False):
        bus.publish({
            "t": 0, "kind": "busy",
            "message": "an audit is already in progress, this one was skipped",
        })
        return
    try:
        bus.publish({
            "t": 0, "kind": "woken",
            "message": f"woken by {source}",
            "workbook": label or os.path.basename(path),
        })
        run = Auditor(on_event=bus.publish).audit(path)
        _sources[run.run_id] = path

        previous = store.previous_for(path, exclude=run.run_id)
        if previous:
            regressions = _regressions(previous, run)
            for line in regressions:
                bus.publish({"t": 0, "kind": "regression", "message": line})

        store.save(run)
        bus.publish({
            "t": round(run.finished_at - run.started_at, 2),
            "kind": "stored",
            "message": f"run {run.run_id} saved to {store.backend}",
            "run_id": run.run_id,
        })
    except Exception as exc:
        bus.publish({
            "t": 0, "kind": "fatal",
            "message": f"audit failed: {type(exc).__name__}: {exc}",
        })
    finally:
        _running.release()


def _regressions(previous: dict[str, Any], run: Any) -> list[str]:
    """Defects present in this revision that were not in the last one."""
    before = {r.get("cell") for r in previous.get("results", [])}
    lines: list[str] = []
    for result in run.results:
        if result.cell not in before and result.status.value in {"repaired", "quarantined"}:
            lines.append(
                f"{result.cell} is newly broken in this revision: {result.explanation}"
            )
    return lines


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "store": store.backend,
        "project": os.environ.get("GOOGLE_CLOUD_PROJECT"),
        "model": os.environ.get("CASSANDRA_MODEL", "gemini-3.5-flash"),
        "vertex": os.environ.get("GOOGLE_GENAI_USE_VERTEXAI"),
    }


@app.post("/pubsub")
async def pubsub(request: Request) -> JSONResponse:
    """Push endpoint for the bucket notification.

    Always answers 204. A non 2xx tells Pub/Sub to redeliver, and redelivering a
    message this service has already handled or cannot ever handle only burns
    the model budget.
    """
    try:
        envelope = await request.json()
    except Exception:
        return JSONResponse({"skipped": "unparseable body"}, status_code=204)

    message = envelope.get("message", {}) if isinstance(envelope, dict) else {}
    attributes = message.get("attributes", {}) or {}
    message_id = message.get("messageId") or message.get("message_id") or ""

    name = attributes.get("objectId", "")
    bucket = attributes.get("bucketId", BUCKET)
    if not name and message.get("data"):
        try:
            payload = json.loads(base64.b64decode(message["data"]).decode())
            name = payload.get("name", "")
            bucket = payload.get("bucket", bucket)
        except Exception:
            pass

    if not name.lower().endswith((".xlsx", ".xlsm")):
        return JSONResponse({"skipped": f"not a workbook: {name}"}, status_code=204)

    if not store.claim(message_id):
        bus.publish({
            "t": 0, "kind": "duplicate",
            "message": f"delivery {message_id} already handled, ignoring",
        })
        return JSONResponse({"skipped": "duplicate delivery"}, status_code=204)

    def work() -> None:
        try:
            local = _download(bucket, name)
        except Exception as exc:
            bus.publish({
                "t": 0, "kind": "fatal",
                "message": f"could not download gs://{bucket}/{name}: {exc}",
            })
            return
        _audit(local, f"gs://{bucket}/{name}")

    threading.Thread(target=work, daemon=True).start()
    return JSONResponse({"accepted": name}, status_code=204)


@app.post("/api/audit")
async def audit_local(request: Request) -> dict[str, Any]:
    """Kick off an audit of a workbook already on disk. Used for local demos."""
    body = await request.json()
    path = body.get("path", "demo/saas_projection_v11.xlsx")
    if not os.path.exists(path):
        return {"error": f"no such workbook: {path}"}
    threading.Thread(target=_audit, args=(path, path), daemon=True).start()
    return {"started": path}


def _start(src: sources.Source) -> dict[str, Any]:
    """Begin an audit of a workbook that is already on disk."""
    if _running.locked():
        return {"error": "An audit is already running. Wait for it to finish."}
    threading.Thread(
        target=_audit, args=(src.path, src.origin, src.name), daemon=True
    ).start()
    return {"started": src.name, "origin": src.origin}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> JSONResponse:
    """Audit a workbook uploaded from the page."""
    try:
        src = sources.from_upload(file.filename or "workbook.xlsx", await file.read())
    except sources.SourceError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(_start(src))


@app.post("/api/import")
async def import_sheet(url: str = Form(...)) -> JSONResponse:
    """Audit a Google Sheet from its link."""
    try:
        src = sources.from_google_sheet(url)
    except sources.SourceError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(_start(src))


@app.get("/api/runs/{run_id}/corrected")
def corrected(run_id: str):
    """Download the workbook with every verified correction applied.

    This is the artifact that makes Cassandra a tool rather than a report. Only
    corrections that passed recalculation are written; anything quarantined or
    awaiting a human is deliberately left alone.
    """
    run = store.get(run_id)
    if not run:
        return JSONResponse({"error": "not found"}, status_code=404)

    patches = {
        r["cell"]: r["final_formula"]
        for r in (run.get("results") or [])
        if r.get("status") == "repaired" and r.get("final_formula")
    }
    if not patches:
        return JSONResponse({"error": "This run produced no verified corrections."}, status_code=400)

    source_path = _sources.get(run_id) or run.get("workbook", "")
    try:
        out = sources.corrected_copy(source_path, patches)
    except sources.SourceError as exc:
        return JSONResponse({"error": str(exc)}, status_code=410)
    except Exception as exc:
        return JSONResponse({"error": f"Could not build the file: {exc}"}, status_code=500)

    return FileResponse(
        out,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=os.path.basename(out),
    )


@app.get("/api/runs")
def runs() -> list[dict[str, Any]]:
    return store.recent()


@app.get("/api/runs/{run_id}")
def run_detail(run_id: str) -> JSONResponse:
    """One run, trimmed to what the interface actually renders.

    Returned through JSONResponse rather than as a plain dict so the body and
    its Content-Length are produced in one pass. Values that arrive from
    Firestore as numpy scalars serialize to a different byte length than
    FastAPI's default encoder measures, which raises a protocol error mid
    response and truncates it.
    """
    run = store.get(run_id)
    if not run:
        return JSONResponse({"error": "not found"}, status_code=404)

    trimmed = {
        k: run.get(k)
        for k in (
            "run_id", "workbook", "started_at", "finished_at",
            "sheets", "cell_count", "formula_count", "headline",
        )
    }
    trimmed["results"] = [
        {
            "cell": r.get("cell"),
            "status": r.get("status"),
            "severity": r.get("severity"),
            "explanation": r.get("explanation"),
            "summary": r.get("summary"),
            "original_formula": r.get("original_formula"),
            "final_formula": r.get("final_formula"),
            "value_before": r.get("value_before"),
            "value_after": r.get("value_after"),
            "needs_human_intent": r.get("needs_human_intent"),
            "attempts": [
                {"attempt": a.get("attempt"), "passed": a.get("passed"),
                 "reason": a.get("reason"), "formula": a.get("formula"),
                 "latent": a.get("latent")}
                for a in (r.get("attempts") or [])
            ],
        }
        for r in (run.get("results") or [])
    ]
    return JSONResponse(json.loads(json.dumps(trimmed, default=_plain)))


def _plain(value: Any) -> Any:
    """Coerce anything the encoder cannot handle, numpy scalars especially."""
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except Exception:
            pass
    return str(value)


@app.post("/api/dismiss/{cell}")
def dismiss(cell: str) -> dict[str, Any]:
    store.dismiss(cell)
    return {"dismissed": cell}


@app.get("/events")
def events() -> StreamingResponse:
    """Server sent events carrying the live reasoning chain to the dashboard."""

    def stream():
        q = bus.subscribe()
        try:
            yield ": connected\n\n"
            while True:
                try:
                    event = q.get(timeout=15)
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    with open(os.path.join(HERE, "static", "index.html"), encoding="utf-8") as handle:
        return handle.read()
