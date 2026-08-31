"""Run persistence, and the idempotency guard around it.

Firestore holds every run, so a worker that dies mid audit loses nothing that
matters and the dashboard can be reopened days later against a finished run.

The idempotency guard exists because Pub/Sub delivers at least once, not
exactly once. A redelivered message must not start a second audit of the same
workbook: it wastes the model budget, and if repairs were ever written back it
would apply them twice. The claim is a Firestore create, which fails if the
document already exists, so two workers racing on the same message produce one
winner without needing a lock.

When Firestore is unreachable the store degrades to memory rather than failing
the request. An audit that ran and was not recorded is worth more than one that
never ran, and the dashboard still works for the session.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict
from typing import Any

RUNS = "cassandra_runs"
CLAIMS = "cassandra_deliveries"


class Store:
    def __init__(self, project: str | None = None):
        self.project = project or os.environ.get("GCP_PROJECT_ID")
        self._memory: dict[str, dict[str, Any]] = {}
        self._claims: set[str] = set()
        self._lock = threading.Lock()
        self._db = None
        try:
            from google.cloud import firestore

            self._db = firestore.Client(project=self.project)
        except Exception:
            self._db = None

    @property
    def backend(self) -> str:
        return "firestore" if self._db is not None else "memory"

    def claim(self, message_id: str) -> bool:
        """True if this delivery is ours to process, False if already handled."""
        if not message_id:
            return True
        if self._db is None:
            with self._lock:
                if message_id in self._claims:
                    return False
                self._claims.add(message_id)
                return True
        try:
            self._db.collection(CLAIMS).document(message_id).create(
                {"claimed_at": time.time()}
            )
            return True
        except Exception:
            # create() raises when the document exists, which is the duplicate
            # case and the whole point. Any other failure also lands here, and
            # declining to process twice is the safe reading of an unknown.
            return False

    def save(self, run: Any) -> None:
        payload = json.loads(run.to_json()) if hasattr(run, "to_json") else asdict(run)
        with self._lock:
            self._memory[payload["run_id"]] = payload
        if self._db is None:
            return
        try:
            self._db.collection(RUNS).document(payload["run_id"]).set(payload)
        except Exception:
            pass

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            if run_id in self._memory:
                return self._memory[run_id]
        if self._db is None:
            return None
        try:
            doc = self._db.collection(RUNS).document(run_id).get()
            return doc.to_dict() if doc.exists else None
        except Exception:
            return None

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if self._db is not None:
            try:
                docs = (
                    self._db.collection(RUNS)
                    .order_by("started_at", direction="DESCENDING")
                    .limit(limit)
                    .stream()
                )
                rows = [d.to_dict() for d in docs]
            except Exception:
                rows = []
        if not rows:
            with self._lock:
                rows = sorted(
                    self._memory.values(),
                    key=lambda r: r.get("started_at", 0),
                    reverse=True,
                )[:limit]
        return [
            {
                "run_id": r.get("run_id"),
                "workbook": r.get("workbook"),
                "started_at": r.get("started_at"),
                "findings": len(r.get("results", [])),
                "repaired": sum(
                    1 for x in r.get("results", []) if x.get("status") == "repaired"
                ),
                "headline": r.get("headline", {}),
            }
            for r in rows
        ]

    def previous_for(self, workbook: str, exclude: str = "") -> dict[str, Any] | None:
        """The most recent earlier run of the same workbook, for regression diffing."""
        base = os.path.basename(workbook or "")
        candidates = [
            r for r in self.recent(50)
            if os.path.basename(r.get("workbook") or "") == base
            and r.get("run_id") != exclude
        ]
        if not candidates:
            return None
        return self.get(candidates[0]["run_id"])

    def delete(self, run_id: str) -> bool:
        """Forget a run entirely, so it stops appearing in the history."""
        removed = False
        with self._lock:
            if run_id in self._memory:
                del self._memory[run_id]
                removed = True
        if self._db is None:
            return removed
        try:
            self._db.collection(RUNS).document(run_id).delete()
            return True
        except Exception:
            return removed

    def dismissals(self) -> set[str]:
        """Cells a human has already dismissed, so the system stops re raising them."""
        if self._db is None:
            return set()
        try:
            docs = self._db.collection("cassandra_dismissals").stream()
            return {d.id.replace("__", "!") for d in docs}
        except Exception:
            return set()

    def dismiss(self, cell: str, reason: str = "") -> None:
        if self._db is None:
            return
        try:
            self._db.collection("cassandra_dismissals").document(
                cell.replace("!", "__")
            ).set({"cell": cell, "reason": reason, "at": time.time()})
        except Exception:
            pass
