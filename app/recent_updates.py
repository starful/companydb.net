"""Recently-updated filing badge — backs the company page's auto-exposed badge.

Reads output/recent_updates.json, written periodically by
script/check_filing_updates.py, and serves it to the small badge widget
rendered by recent_update_badge_html() / recent_update_script() in
script/build_company_page.py.
"""

from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, jsonify

recent_updates_bp = Blueprint("recent_updates", __name__)

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "output" / "recent_updates.json"


def _load_state() -> dict:
    if not STATE_PATH.is_file():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


@recent_updates_bp.get("/api/recent-updates")
def all_recent_updates():
    return jsonify(_load_state())


@recent_updates_bp.get("/api/recent-updates/<ticker>")
def recent_update_for(ticker: str):
    entry = _load_state().get(ticker)
    if not entry:
        return jsonify({"has_update": False})
    return jsonify(entry)
