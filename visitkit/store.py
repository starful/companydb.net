"""SQLite (local) · optional Firestore when STORE_BACKEND=firestore."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

KEEP_DAYS = 90
DAILY_MAX = 600

_store: Any = None
_store_lock = threading.Lock()
_counts: dict[str, tuple[str, int]] = {}
_counts_lock = threading.Lock()


def allow(vid: str, n: int) -> bool:
    day = time.strftime("%Y%m%d")
    with _counts_lock:
        d, used = _counts.get(vid, (day, 0))
        if d != day:
            used = 0
        if used + n > DAILY_MAX:
            return False
        if len(_counts) > 50000:
            _counts.clear()
        _counts[vid] = (day, used + n)
        return True


class SqliteVisitStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        import sqlite3
        with sqlite3.connect(path) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS visit_events "
                "(vid TEXT, at INTEGER, e TEXT, p TEXT, path TEXT, ref TEXT, lang TEXT)"
            )
            db.execute("CREATE INDEX IF NOT EXISTS visit_events_at ON visit_events (at)")

    def add_events(self, rows: list[dict[str, Any]]) -> None:
        import sqlite3
        cutoff = int(time.time()) - KEEP_DAYS * 86400
        with self._lock, sqlite3.connect(self.path) as db:
            db.executemany(
                "INSERT INTO visit_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(r["vid"], r["at"], r["e"], json.dumps(r["p"], ensure_ascii=False),
                  r["path"], r["ref"], r["lang"]) for r in rows],
            )
            db.execute("DELETE FROM visit_events WHERE at < ?", (cutoff,))

    def events_since(self, since: int) -> list[dict[str, Any]]:
        import sqlite3
        with sqlite3.connect(self.path) as db:
            cur = db.execute(
                "SELECT vid, at, e, p, path, ref, lang FROM visit_events WHERE at >= ? ORDER BY at",
                (since,),
            )
            return [
                {"vid": v, "at": a, "e": e, "p": json.loads(p or "{}"), "path": pa, "ref": rf, "lang": lg}
                for v, a, e, p, pa, rf, lg in cur.fetchall()
            ]


class FirestoreVisitStore:
    """{FIRESTORE_COLLECTION}/visits/rows — same shape as SiteKPI visits."""

    def __init__(self, client: Any | None = None) -> None:
        from google.cloud import firestore  # type: ignore

        root = (os.getenv("FIRESTORE_COLLECTION") or "okpy").strip() or "okpy"
        self._db = client or firestore.Client(
            project=(os.getenv("FIRESTORE_PROJECT") or "").strip() or None
        )
        self._col = self._db.collection(root).document("visits").collection("rows")

    @staticmethod
    def _exp(at: int):
        import datetime as dt
        return dt.datetime.fromtimestamp(at + KEEP_DAYS * 86400, tz=dt.timezone.utc)

    def add_events(self, rows: list[dict[str, Any]]) -> None:
        for r in rows:
            self._col.add({**r, "expire_at": self._exp(r["at"])})

    def events_since(self, since: int) -> list[dict[str, Any]]:
        try:
            from google.cloud.firestore_v1.base_query import FieldFilter
            q = self._col.where(filter=FieldFilter("at", ">=", since))
        except Exception:
            q = self._col.where("at", ">=", since)
        out = []
        for snap in q.stream():
            d = snap.to_dict() or {}
            d.pop("expire_at", None)
            if "p" in d and isinstance(d["p"], str):
                try:
                    d["p"] = json.loads(d["p"])
                except json.JSONDecodeError:
                    d["p"] = {}
            out.append(d)
        return sorted(out, key=lambda d: d.get("at", 0))


def configure_store(*, db_path: Path | None = None, force: Any | None = None) -> Any:
    global _store
    with _store_lock:
        if force is not None:
            _store = force
            return _store
        if (os.getenv("STORE_BACKEND") or "").strip().lower() == "firestore":
            _store = FirestoreVisitStore()
        else:
            path = db_path or Path(os.getenv("VISITLOG_DB") or ".data/visitlog.sqlite3")
            _store = SqliteVisitStore(Path(path))
        return _store


def get_store() -> Any:
    global _store
    if _store is None:
        return configure_store()
    return _store
