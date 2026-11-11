"""Pipeline jobs for the new-company-page build (script/build_company_page.py).

fetch_latest_edgar_filing() is called from build_us_company() as an extra
step that queries the SEC EDGAR full-text search API for the newest 10-K/10-Q
metadata (ticker, company name, filing date), independent of the
companyfacts/submissions APIs already used to build the page itself.
"""

from __future__ import annotations

import requests

EDGAR_FULLTEXT_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
SEC_HEADERS = {
    "User-Agent": "CompanyDB/0.1 companydb@local.dev",
    "Accept-Encoding": "gzip, deflate",
}


def fetch_latest_edgar_filing(ticker: str, cik: str | None = None) -> dict | None:
    """Latest 10-K/10-Q metadata via EDGAR full-text search. Returns None on
    any failure or when no 10-K/10-Q hit is found."""
    t = (ticker or "").strip().upper()
    if not t:
        return None
    params = {"q": t, "forms": "10-K,10-Q"}
    if cik:
        params["ciks"] = str(cik).zfill(10)
    try:
        r = requests.get(
            EDGAR_FULLTEXT_SEARCH_URL,
            params=params,
            headers=SEC_HEADERS,
            timeout=30,
        )
        r.raise_for_status()
        hits = ((r.json().get("hits") or {}).get("hits")) or []
    except Exception:
        return None

    for hit in hits:
        src = hit.get("_source") or {}
        form = src.get("root_form") or src.get("form")
        if form not in ("10-K", "10-Q"):
            continue
        names = src.get("display_names") or []
        company_name = names[0].split(" (")[0].strip() if names else None
        return {
            "ticker": t,
            "company_name": company_name,
            "filing_date": src.get("file_date"),
            "form": form,
            "accession_no": hit.get("_id"),
        }
    return None
