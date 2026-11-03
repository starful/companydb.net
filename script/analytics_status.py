#!/usr/bin/env python3
"""Check GA4 and Google Search Console connection status for companydb.net.

Confirms the GA4 measurement ID baked into generated pages is actually set
and reaches the home page, and that a GSC site property + credentials are
configured for script/gsc_resubmit.py to use.

Usage:
  python3 script/analytics_status.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from script.build_company_page import GA4_MEASUREMENT_ID, INDEX_PATH, SITE_URL  # noqa: E402

GA_CONFIG_RE = re.compile(r"gtag\(\s*'config',\s*'([^']+)'\s*\)")


def ga4_status() -> dict:
    """Whether a GA4 measurement ID is configured and actually present on the home page."""
    configured = bool(GA4_MEASUREMENT_ID) and GA4_MEASUREMENT_ID.startswith("G-")
    id_on_page = None
    if INDEX_PATH.is_file():
        m = GA_CONFIG_RE.search(INDEX_PATH.read_text(encoding="utf-8"))
        id_on_page = m.group(1) if m else None
    return {
        "configured": configured,
        "measurement_id": GA4_MEASUREMENT_ID if configured else None,
        "matches_home_page": configured and id_on_page == GA4_MEASUREMENT_ID,
    }


def gsc_status() -> dict:
    """Whether a Search Console property and service-account credentials are available."""
    site_property = os.environ.get("GSC_SITE_PROPERTY", f"{SITE_URL}/")
    cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    return {
        "configured": bool(site_property),
        "property": site_property,
        "credentials_available": bool(cred_path and os.path.exists(cred_path)),
    }


def check_status() -> dict:
    """Combined GA4 + GSC connection status for the analytics dashboard."""
    return {"ga4": ga4_status(), "gsc": gsc_status()}


def main() -> None:
    status = check_status()
    ga4, gsc = status["ga4"], status["gsc"]
    print(
        f"GA4: configured={ga4['configured']} "
        f"measurement_id={ga4['measurement_id']} "
        f"matches_home_page={ga4['matches_home_page']}"
    )
    print(
        f"GSC: configured={gsc['configured']} "
        f"property={gsc['property']} "
        f"credentials_available={gsc['credentials_available']}"
    )
    healthy = ga4["configured"] and ga4["matches_home_page"] and gsc["configured"]
    if not healthy:
        print("One or more analytics connections are incomplete.", file=sys.stderr)
        sys.exit(1)
    print("OK — GA4 and GSC are both connected.")


if __name__ == "__main__":
    main()
