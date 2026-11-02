#!/usr/bin/env python3
"""Audit sitemap/canonical/robots health — run before resubmitting to Search Console.

Checks the three likely causes of a sitemap stuck at 0 discovered/indexed URLs:
  1. every sitemap.xml URL resolves to a real file whose canonical self-references it
  2. no two pages share the same canonical URL (a classic duplicate-content signal)
  3. robots.txt does not Disallow a path the sitemap lists, and no page carries noindex

Usage:
  python3 script/seo_audit.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from script.build_company_page import (  # noqa: E402
    COMPARE_PATH,
    INDEX_PATH,
    OUT_DIR,
    ROBOTS_PATH,
    SITEMAP_PATH,
)

CANONICAL_RE = re.compile(r'<link rel="canonical" href="([^"]+)"')
SITEMAP_LOC_RE = re.compile(r"<loc>([^<]+)</loc>")
NOINDEX_RE = re.compile(r"noindex", re.IGNORECASE)


def _path_for_url(url: str) -> Path | None:
    """Map a sitemap URL to the on-disk file that should serve it."""
    path = urlparse(url).path
    if path in ("/", "/index.html"):
        return INDEX_PATH
    if path == "/compare.html":
        return COMPARE_PATH
    if path.startswith("/companies/"):
        return OUT_DIR / path[len("/companies/") :]
    return None


def _disallowed_rules() -> list[str]:
    if not ROBOTS_PATH.is_file():
        return []
    rules = []
    for line in ROBOTS_PATH.read_text(encoding="utf-8").splitlines():
        if line.lower().startswith("disallow:"):
            rule = line.split(":", 1)[1].strip()
            if rule:
                rules.append(rule)
    return rules


def audit() -> list[str]:
    """Returns a list of problem descriptions; empty means healthy."""
    if not SITEMAP_PATH.is_file():
        return [f"missing {SITEMAP_PATH}"]

    sitemap_urls = SITEMAP_LOC_RE.findall(SITEMAP_PATH.read_text(encoding="utf-8"))
    if not sitemap_urls:
        return ["sitemap.xml has zero <url> entries"]

    disallow = _disallowed_rules()
    problems: list[str] = []
    canonical_owner: dict[str, str] = {}

    for url in sitemap_urls:
        path = urlparse(url).path
        for rule in disallow:
            if path.startswith(rule):
                problems.append(f"robots.txt disallows {rule!r}, which blocks sitemap URL {url}")

        page = _path_for_url(url)
        if page is None or not page.is_file():
            problems.append(f"sitemap lists {url} but no file serves it")
            continue

        html = page.read_text(encoding="utf-8")
        if NOINDEX_RE.search(html):
            problems.append(f"{page.relative_to(ROOT)} contains a noindex signal")

        m = CANONICAL_RE.search(html)
        if not m:
            problems.append(f'{page.relative_to(ROOT)} has no <link rel="canonical">')
            continue

        canonical = m.group(1)
        if canonical != url:
            problems.append(f"{url} canonical points to {canonical} instead of itself")
        elif canonical in canonical_owner:
            problems.append(
                f"duplicate canonical {canonical} used by both "
                f"{canonical_owner[canonical]} and {url}"
            )
        canonical_owner[canonical] = url

    return problems


def main() -> None:
    problems = audit()
    if not problems:
        print(f"OK — {SITEMAP_PATH} looks healthy, safe to resubmit to Search Console.")
        return
    print(f"Found {len(problems)} issue(s):")
    for p in problems:
        print(" -", p)
    sys.exit(1)


if __name__ == "__main__":
    main()
