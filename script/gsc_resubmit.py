#!/usr/bin/env python3
"""Batch-resubmit the sitemap and request indexing for priority CompanyDB pages.

Auth follows the same pattern as app/reactions.py: a service-account JSON
pointed at by GOOGLE_APPLICATION_CREDENTIALS, authorized via google-auth
(already installed transitively through firebase-admin — no new dependency).
The service account must be added as an Owner/Full user on the Search
Console property for both calls below to succeed.

Usage:
  python3 script/gsc_resubmit.py --sitemap
  python3 script/gsc_resubmit.py --urls --limit 10
  python3 script/gsc_resubmit.py --sitemap --urls --limit 10 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from script.build_company_page import CATALOG_PATH, OUT_DIR, SITE_URL  # noqa: E402

WEBMASTERS_SCOPE = "https://www.googleapis.com/auth/webmasters"
INDEXING_SCOPE = "https://www.googleapis.com/auth/indexing"


def _authorized_session(scopes: list[str]):
    """Service-account session scoped for one or more Google APIs, or None if unset."""
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not cred_path or not os.path.exists(cred_path):
        print(
            "GOOGLE_APPLICATION_CREDENTIALS not set or file missing — "
            "point it at the same service-account JSON used for Firestore.",
            file=sys.stderr,
        )
        return None
    try:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account
    except ImportError:
        print(
            "google-auth is unavailable — expected it transitively via firebase-admin.",
            file=sys.stderr,
        )
        return None
    creds = service_account.Credentials.from_service_account_file(cred_path, scopes=scopes)
    return AuthorizedSession(creds)


def priority_urls(limit: int) -> list[str]:
    """Home, compare, then the newest `limit` company pages that actually exist."""
    urls = [f"{SITE_URL}/", f"{SITE_URL}/compare.html"]
    if not CATALOG_PATH.exists():
        return urls
    try:
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        catalog = []
    if not isinstance(catalog, list):
        catalog = []
    catalog = sorted(catalog, key=lambda c: str(c.get("added_at") or ""), reverse=True)
    seen: set[str] = set()
    for c in catalog:
        if len(seen) >= limit:
            break
        ticker = str(c.get("ticker") or "").strip()
        if not ticker or ticker in seen or not (OUT_DIR / f"{ticker}.html").is_file():
            continue
        seen.add(ticker)
        urls.append(f"{SITE_URL}/companies/{quote(ticker)}.html")
    return urls


def submit_sitemap(site_property: str, *, dry_run: bool = False) -> bool:
    sitemap_url = f"{SITE_URL}/sitemap.xml"
    endpoint = (
        "https://www.googleapis.com/webmasters/v3/sites/"
        f"{quote(site_property, safe='')}/sitemaps/{quote(sitemap_url, safe='')}"
    )
    if dry_run:
        print("DRY RUN PUT", endpoint)
        return True
    session = _authorized_session([WEBMASTERS_SCOPE])
    if session is None:
        return False
    resp = session.put(endpoint)
    ok = resp.status_code in (200, 204)
    print("sitemap submit", resp.status_code, sitemap_url)
    if not ok:
        print(resp.text[:500], file=sys.stderr)
    return ok


def request_indexing(urls: list[str], *, dry_run: bool = False) -> dict:
    endpoint = "https://indexing.googleapis.com/v3/urlNotifications:publish"
    ok, fail = [], []
    session = None if dry_run else _authorized_session([INDEXING_SCOPE])
    if not dry_run and session is None:
        return {"ok": ok, "fail": [(u, "no credentials") for u in urls]}
    for url in urls:
        if dry_run:
            print("DRY RUN POST", endpoint, url)
            ok.append(url)
            continue
        try:
            resp = session.post(endpoint, json={"url": url, "type": "URL_UPDATED"})
            if resp.status_code == 200:
                print("indexed", url)
                ok.append(url)
            else:
                print("FAIL", resp.status_code, url, resp.text[:200])
                fail.append((url, f"{resp.status_code} {resp.text[:200]}"))
        except Exception as e:
            print("FAIL", url, e)
            fail.append((url, str(e)))
    return {"ok": ok, "fail": fail}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sitemap", action="store_true", help="Resubmit sitemap.xml to Search Console")
    ap.add_argument("--urls", action="store_true", help="Request indexing for priority pages")
    ap.add_argument("--limit", type=int, default=10, help="Company pages to request indexing for")
    ap.add_argument(
        "--property",
        default=os.environ.get("GSC_SITE_PROPERTY", f"{SITE_URL}/"),
        help="Search Console site property (default: SITE_URL as URL-prefix property)",
    )
    ap.add_argument("--dry-run", action="store_true", help="Print requests without calling Google")
    args = ap.parse_args()

    if not args.sitemap and not args.urls:
        ap.error("pass --sitemap and/or --urls")

    if args.sitemap:
        submit_sitemap(args.property, dry_run=args.dry_run)

    if args.urls:
        urls = priority_urls(args.limit)
        result = request_indexing(urls, dry_run=args.dry_run)
        print(f"Indexing requests: ok={len(result['ok'])} fail={len(result['fail'])}")
        for url, err in result["fail"]:
            print(" ", url, err)


if __name__ == "__main__":
    main()
