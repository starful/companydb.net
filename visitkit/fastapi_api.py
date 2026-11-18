"""FastAPI routes: POST /events · GET /hq/api/users · vid cookie on HTML."""

from __future__ import annotations

import hmac
import re
import secrets
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

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


def _vid(request: Request) -> tuple[str, bool]:
    v = request.cookies.get(COOKIE) or ""
    return (v, False) if _VID.match(v) else (secrets.token_hex(12), True)


def _set_cookie(resp: Response, request: Request, vid: str, new: bool) -> Response:
    if new:
        resp.set_cookie(
            COOKIE, vid, max_age=COOKIE_AGE, httponly=True, samesite="lax",
            secure=request.url.scheme == "https", path="/",
        )
    return resp


def register_visitlog(
    app: FastAPI,
    *,
    site_id: str,
    db_path: Path | str | None = None,
) -> None:
    configure_store(db_path=Path(db_path) if db_path else None)
    sid = site_id

    @app.middleware("http")
    async def _visitlog_vid(request: Request, call_next):  # type: ignore[misc]
        response = await call_next(request)
        ctype = response.headers.get("content-type", "")
        if request.method == "GET" and ctype.startswith("text/html"):
            vid, new = _vid(request)
            return _set_cookie(response, request, vid, new)
        return response

    @app.post("/events")
    async def visitlog_events(request: Request):  # type: ignore[misc]
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False}, status_code=400)
        items = body.get("events") if isinstance(body, dict) else None
        if not isinstance(items, list) or not items or len(items) > 20:
            return JSONResponse({"ok": False}, status_code=400)
        vid, new = _vid(request)
        now = int(time.time())
        lang = str(body.get("lang") or "")[:5]
        path = str(body.get("path") or "")[:120].split("?")[0]
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
        resp = JSONResponse({"ok": True})
        return _set_cookie(resp, request, vid, new)

    @app.get("/hq/api/users")
    async def visitlog_hq_users(request: Request, days: int = 7):  # type: ignore[misc]
        want = hq_token(sid)
        if not want:
            return Response(status_code=404)
        got = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
        if not got or not hmac.compare_digest(got, want):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        days = days if days in (7, 30, 90) else 7
        now = int(time.time())
        since = now - days * 86400
        prev_since = since - days * 86400
        store = get_store()
        events = store.events_since(prev_since)
        cur = [r for r in events if r["at"] >= since]
        prev_visitors = len({r["vid"] for r in events if r["at"] < since})
        return JSONResponse(summarize(cur, days=days, now=now, prev_visitors=prev_visitors, keep_days=KEEP_DAYS))
