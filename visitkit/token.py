"""HQ read token: HMAC of VISITLOG_SECRET (or SESSION_SECRET) + site id."""

from __future__ import annotations

import hmac
import os


def derive_hq_token(secret: str, site_id: str) -> str:
    base = (secret or "").strip()
    sid = (site_id or "").strip()
    if not base or not sid:
        return ""
    return hmac.new(base.encode(), f"visitlog-hq-api-v1:{sid}".encode(), "sha256").hexdigest()


def hq_token(site_id: str, *, secret: str | None = None) -> str:
    """Explicit VISITLOG_HQ_TOKEN wins; else derive from VISITLOG_SECRET / SESSION_SECRET."""
    explicit = (os.getenv("VISITLOG_HQ_TOKEN") or "").strip()
    if explicit:
        return explicit
    base = secret if secret is not None else (os.getenv("VISITLOG_SECRET") or os.getenv("SESSION_SECRET") or "")
    return derive_hq_token(base, site_id)
