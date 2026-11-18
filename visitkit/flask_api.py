"""Flask routes: POST /events · GET /hq/api/users · optional vid cookie on HTML."""

from __future__ import annotations

import hmac
import re
import secrets
import time
from pathlib import Path
from typing import Any
from flask import Flask, Request, Response, jsonify, request

from .store import KEEP_DAYS, allow, configure_store, get_store
from .summarize import summarize
from .token import hq_token

COOKIE = "sf_vid"
COOKIE_AGE = 180 * 24 * 3600
_EVENT = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_VID = re.compile(r"^[a-f0-9]{24}$")
PARAM_KEYS = frozenset({
    "screen", "href", "label", "kind", "q",
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
})


def _host(ref: Any) -> str:
    m = re.match(r"^https?://([^/:?#]+)", str(ref or ""))
    return m.group(1).lower()[:80] if m else ""


def _clean_params(raw: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if k in PARAM_KEYS and isinstance(v, (str, int, float, bool)) and len(out) < 12:
                out[k] = str(v)[:80]
    return out


def _vid(req: Request) -> tuple[str, bool]:
    v = req.cookies.get(COOKIE) or ""
    return (v, False) if _VID.match(v) else (secrets.token_hex(12), True)


def _with_cookie(resp: Response, req: Request, vid: str, new: bool) -> Response:
    if new:
        resp.set_cookie(
            COOKIE, vid, max_age=COOKIE_AGE, httponly=True, samesite="Lax",
            secure=req.is_secure, path="/",
        )
    return resp


def register_visitlog(
    app: Flask,
    *,
    site_id: str,
    db_path: Path | str | None = None,
) -> None:
    """Attach /events and /hq/api/users. Set cookie on HTML GET."""
    configure_store(db_path=Path(db_path) if db_path else None)
    sid = site_id

    @app.after_request
    def _visitlog_set_vid(resp: Response):  # type: ignore[misc]
        if request.method == "GET" and (resp.content_type or "").startswith("text/html"):
            vid, new = _vid(request)
            return _with_cookie(resp, request, vid, new)
        return resp

    @app.post("/events")
    def visitlog_events():  # type: ignore[misc]
        body = request.get_json(silent=True) or {}
        items = body.get("events") if isinstance(body, dict) else None
        if not isinstance(items, list) or not items or len(items) > 20:
            return jsonify({"ok": False}), 400
        vid, new = _vid(request)
        now = int(time.time())
        lang = str(body.get("lang") or "")[:5]
        path = str(body.get("path") or "")[:120].split("?")[0]
        # UTM from page query (track.js also puts on pv params)
        rows = []
        for it in items:
            if not isinstance(it, dict) or not _EVENT.match(str(it.get("e") or "")):
                continue
            rows.append({
                "vid": vid, "at": now, "e": it["e"], "p": _clean_params(it.get("p")),
                "path": path, "ref": _host(it.get("ref")), "lang": lang,
            })
        if rows and allow(vid, len(rows)):
            get_store().add_events(rows)
        return _with_cookie(jsonify({"ok": True}), request, vid, new)

    @app.get("/hq/api/users")
    def visitlog_hq_users():  # type: ignore[misc]
        want = hq_token(sid)
        if not want:
            return Response(status=404)
        got = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
        if not got or not hmac.compare_digest(got, want):
            return jsonify({"error": "unauthorized"}), 401
        try:
            days = int(request.args.get("days") or 7)
        except ValueError:
            days = 7
        days = days if days in (7, 30, 90) else 7
        now = int(time.time())
        since = now - days * 86400
        prev_since = since - days * 86400
        store = get_store()
        events = store.events_since(prev_since)
        cur = [r for r in events if r["at"] >= since]
        prev_visitors = len({r["vid"] for r in events if r["at"] < since})
        return jsonify(summarize(cur, days=days, now=now, prev_visitors=prev_visitors, keep_days=KEEP_DAYS))
