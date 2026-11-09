#!/usr/bin/env python3
"""Poll EDINET / DART / SEC for a filing newer than what's already on file and
flag a 'Recently updated' badge + diff summary for the company page.

data/catalog.json (built by script/build_company_page.py) is the baseline —
whatever doc_id / filing_date is recorded there is treated as "known". Any
filing found by the APIs below that is newer is written to
output/recent_updates.json, which app/recent_updates.py serves to the badge
widget rendered by recent_update_badge_html() / recent_update_script().

Intended to run on a schedule (cron, Task Scheduler, etc.):
  python3 script/check_filing_updates.py
  python3 script/check_filing_updates.py --market JP --max-days 10
  python3 script/check_filing_updates.py --ticker 7203 --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from script.build_company_page import (  # noqa: E402
    CATALOG_PATH,
    DART_API,
    EDINET_LIST,
    _normalize_sec,
    load_api_key,
    load_opendart_key,
    resolve_dart_corp_code,
    resolve_sec_cik,
    sec_fetch_submissions,
)

OUTPUT = ROOT / "output"
STATE_PATH = OUTPUT / "recent_updates.json"


def load_catalog() -> list[dict]:
    if not CATALOG_PATH.exists():
        return []
    try:
        return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def save_state(state: dict) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def edinet_latest_filing(key: str, ticker: str, max_days: int) -> dict | None:
    """Newest EDINET annual securities report for ticker within the scan window."""
    want = _normalize_sec(ticker)
    for i in range(1, max_days + 1):
        d = (date.today() - timedelta(days=i)).isoformat()
        try:
            r = requests.get(
                EDINET_LIST,
                params={"date": d, "type": 2, "Subscription-Key": key},
                timeout=60,
            )
            r.raise_for_status()
        except Exception:
            continue
        for x in r.json().get("results") or []:
            if (
                x.get("ordinanceCode") == "010"
                and x.get("formCode") == "030000"
                and x.get("secCode") == want
                and str(x.get("xbrlFlag")) == "1"
            ):
                return {
                    "doc_id": x.get("docID"),
                    "filing_date": d,
                    "description": x.get("docDescription") or "Annual securities report",
                }
    return None


def dart_latest_filing(key: str, corp_code: str, max_days: int) -> dict | None:
    """Newest Open DART periodic disclosure for corp_code within the scan window."""
    end_de = date.today().strftime("%Y%m%d")
    bgn_de = (date.today() - timedelta(days=max_days)).strftime("%Y%m%d")
    try:
        r = requests.get(
            f"{DART_API}/list.json",
            params={
                "crtfc_key": key,
                "corp_code": corp_code,
                "bgn_de": bgn_de,
                "end_de": end_de,
                "pblntf_ty": "A",  # periodic disclosures (annual/semi/quarterly reports)
                "page_count": 10,
            },
            timeout=60,
        )
        r.raise_for_status()
    except Exception:
        return None
    data = r.json()
    if data.get("status") != "000":
        return None
    rows = data.get("list") or []
    if not rows:
        return None
    row = rows[0]  # DART returns newest-first
    return {
        "doc_id": row.get("rcept_no"),
        "filing_date": row.get("rcept_dt"),
        "description": row.get("report_nm") or "Periodic disclosure",
    }


def sec_latest_filing(cik: str) -> dict | None:
    """Newest 10-K / 10-K/A / 10-Q from SEC submissions (already newest-first)."""
    try:
        submissions = sec_fetch_submissions(cik)
    except Exception:
        return None
    recent = (submissions.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    accessions = recent.get("accessionNumber") or []
    filing_dates = recent.get("filingDate") or []
    for form, acc, fdate in zip(forms, accessions, filing_dates):
        if form in ("10-K", "10-K/A", "10-Q"):
            return {"doc_id": acc, "filing_date": fdate, "description": form}
    return None


def check_one(entry: dict, *, max_days: int, edinet_key: str | None, dart_key: str | None) -> dict | None:
    """Compare one catalog entry against its market's API. Returns an
    output/recent_updates.json record, or None if nothing newer was found."""
    ticker = str(entry.get("ticker") or "").strip()
    market = str(entry.get("market") or "").strip().upper()
    old_doc_id = entry.get("doc_id")
    if not ticker or not market:
        return None

    latest = None
    if market == "JP" and edinet_key:
        latest = edinet_latest_filing(edinet_key, ticker, max_days)
    elif market == "KR" and dart_key:
        corp_code = resolve_dart_corp_code(ticker)
        if corp_code:
            latest = dart_latest_filing(dart_key, corp_code, max_days)
    elif market == "US":
        cik = resolve_sec_cik(ticker)
        if cik:
            latest = sec_latest_filing(cik)

    if not latest or not latest.get("doc_id") or latest["doc_id"] == old_doc_id:
        return None

    company_en = entry.get("company_en") or ticker
    diff_summary = (
        f"{latest.get('description') or 'A new filing'} for {company_en} "
        f"was filed {latest.get('filing_date') or 'recently'} — the figures on this page "
        f"are still from {entry.get('filing_date') or 'an earlier filing'}."
    )
    return {
        "ticker": ticker,
        "market": market,
        "company_en": company_en,
        "has_update": True,
        "detected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "previous": {
            "doc_id": old_doc_id,
            "filing_date": entry.get("filing_date"),
            "period_end": entry.get("period_end"),
        },
        "latest": latest,
        "diff_summary": diff_summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", choices=["JP", "KR", "US"], help="Only check this market")
    parser.add_argument("--ticker", help="Only check this ticker")
    parser.add_argument("--max-days", type=int, default=14, help="Scan window in days (default 14)")
    parser.add_argument("--dry-run", action="store_true", help="Print results, don't write state")
    args = parser.parse_args()

    try:
        edinet_key = load_api_key()
    except SystemExit:
        edinet_key = None
        print("EDINET_API_KEY missing — skipping JP checks.", file=sys.stderr)
    try:
        dart_key = load_opendart_key()
    except SystemExit:
        dart_key = None
        print("OPENDART_API_KEY missing — skipping KR checks.", file=sys.stderr)

    catalog = load_catalog()
    if args.market:
        catalog = [c for c in catalog if str(c.get("market") or "").upper() == args.market]
    if args.ticker:
        catalog = [c for c in catalog if str(c.get("ticker") or "") == args.ticker]

    new_state: dict[str, dict] = {}
    for entry in catalog:
        record = check_one(entry, max_days=args.max_days, edinet_key=edinet_key, dart_key=dart_key)
        if record:
            new_state[record["ticker"]] = record
            print("UPDATE", record["ticker"], record["diff_summary"], flush=True)

    print(f"Checked {len(catalog)} companies, {len(new_state)} with a newer filing.")
    if not args.dry_run:
        save_state(new_state)
        print("Wrote", STATE_PATH, flush=True)


if __name__ == "__main__":
    main()
