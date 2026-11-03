"""GA4 / GSC connection status — backs the analytics dashboard."""

from __future__ import annotations

from flask import Blueprint, jsonify

from script.analytics_status import check_status

analytics_status_bp = Blueprint("analytics_status", __name__)


@analytics_status_bp.get("/api/analytics-status")
def analytics_status():
    return jsonify(check_status())
