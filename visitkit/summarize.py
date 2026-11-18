"""HQ popup payload for content sites (no survey)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta, timezone
from itertools import pairwise
from typing import Any

JST = timezone(timedelta(hours=9))

# (label, predicate on one event row)
DEFAULT_FUNNEL: tuple[tuple[str, Callable[[dict[str, Any]], bool]], ...] = (
    ("홈", lambda r: r["e"] == "pv" and _is_home(r.get("path") or "")),
    ("콘텐츠", lambda r: r["e"] == "pv" and _is_content(r.get("path") or "")),
    ("CTA·외부", lambda r: r["e"] in ("cta", "outbound", "affiliate")),
)


def _is_home(path: str) -> bool:
    p = (path or "/").rstrip("/") or "/"
    return p in ("/", "/index", "/index.html", "/ja", "/en", "/ko")


def _is_content(path: str) -> bool:
    if _is_home(path):
        return False
    p = path or ""
    return any(p.startswith(x) for x in (
        "/blog/", "/category/", "/guide/", "/item/", "/posts/",
        "/university/", "/school/", "/company/", "/spot/", "/onsen/",
        "/course/", "/wall",
    )) or (p.count("/") >= 1 and p not in ("/about.html", "/privacy.html", "/contact.html", "/contact", "/robots.txt"))


def _short(vid: str) -> str:
    return (vid or "")[:4]


def _hm(at: int) -> str:
    return datetime.fromtimestamp(at, JST).strftime("%H:%M")


def _md_hm(at: int) -> str:
    return datetime.fromtimestamp(at, JST).strftime("%m-%d %H:%M")


def _sessions(ats: Iterable[int]) -> int:
    n, last = 0, None
    for a in sorted(ats):
        if last is None or a - last > 30 * 60:
            n += 1
        last = a
    return n


def _what(r: dict[str, Any]) -> tuple[str, str, str]:
    e, p = r["e"], r.get("p") or {}
    path = r.get("path") or ""
    if e == "pv":
        if _is_home(path):
            return "홈", path, ""
        if _is_content(path):
            return "콘텐츠", path, "key"
        return "페이지", path, ""
    if e in ("cta", "outbound", "affiliate"):
        return "CTA·외부", str(p.get("href") or p.get("label") or "")[:80], "key"
    if e == "click":
        return "클릭", str(p.get("label") or p.get("href") or "")[:80], ""
    if e == "search":
        return "검색", str(p.get("q") or "")[:60], ""
    return e, path, ""


def _did(rows: list[dict[str, Any]]) -> str:
    bits = []
    if any(r["e"] == "pv" and _is_content(r.get("path") or "") for r in rows):
        bits.append("콘텐츠")
    if any(r["e"] in ("cta", "outbound", "affiliate") for r in rows):
        bits.append("CTA")
    if any(r["e"] == "search" for r in rows):
        bits.append("검색")
    return " · ".join(bits) or "둘러봄"


def summarize(
    events: list[dict[str, Any]],
    *,
    days: int,
    now: int,
    prev_visitors: int = 0,
    funnel: tuple[tuple[str, Callable[[dict[str, Any]], bool]], ...] | None = None,
    keep_days: int = 90,
) -> dict[str, Any]:
    by_vid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in events:
        by_vid[r["vid"]].append(r)
    visitors = len(by_vid)
    pct = lambda n, d: f"{round(n / d * 100)}%" if d else "—"

    content_n = sum(1 for rows in by_vid.values() if any(r["e"] == "pv" and _is_content(r.get("path") or "") for r in rows))
    cta_n = sum(1 for rows in by_vid.values() if any(r["e"] in ("cta", "outbound", "affiliate") for r in rows))
    return_n = sum(1 for rows in by_vid.values() if _sessions(r["at"] for r in rows) >= 2)

    kpis = [
        {"label": "방문자", "value": visitors, "unit": "명", "note": f"이전 {days}일 {prev_visitors}명"},
        {"label": "콘텐츠 본 사람", "value": content_n, "unit": "명", "note": f"방문자의 {pct(content_n, visitors)}"},
        {"label": "CTA·외부 클릭", "value": cta_n, "unit": "명", "note": f"방문자의 {pct(cta_n, visitors)}"},
        {"label": "재방문", "value": return_n, "unit": "명", "note": f"방문자의 {pct(return_n, visitors)}"},
    ]

    steps = funnel or DEFAULT_FUNNEL
    funnel_rows = []
    for label, pred in steps:
        n = sum(1 for rows in by_vid.values() if any(pred(r) for r in rows))
        funnel_rows.append({"label": label, "n": n, "pct": pct(n, visitors)})

    stuck = ""
    worst = None
    for a, b in pairwise(funnel_rows):
        if a["n"] and (worst is None or a["n"] - b["n"] > worst[2]):
            worst = (a, b, a["n"] - b["n"])
    if worst and worst[2] > 0:
        stuck = f"가장 많이 멈추는 곳: {worst[0]['label']} → {worst[1]['label']} ({worst[0]['n']}명 중 {worst[1]['n']}명)"

    people = []
    for vid, rows in sorted(by_vid.items(), key=lambda kv: -kv[1][-1]["at"])[:100]:
        first = rows[0]
        ref = next((r["ref"] for r in rows if r.get("ref")), "")
        utm = next((r.get("p", {}).get("utm_source") for r in rows if (r.get("p") or {}).get("utm_source")), "")
        from_label = ref or (f"utm:{utm}" if utm else "직접")
        timeline = []
        for r in rows[-60:]:
            what, where, tone = _what(r)
            timeline.append({"at": _hm(r["at"]), "what": what, "where": where, "tone": tone})
        people.append({
            "id": _short(vid),
            "first": _md_hm(first["at"]),
            "last": _md_hm(rows[-1]["at"]),
            "from": from_label,
            "why": "—",
            "role": "",
            "did": _did(rows),
            "visits": _sessions(r["at"] for r in rows),
            "lang": first.get("lang", ""),
            "steps": timeline,
        })

    return {
        "days": days,
        "generated_at": _md_hm(now),
        "kpis": kpis,
        "funnel": funnel_rows,
        "stuck": stuck,
        "survey": [],
        "answered": 0,
        "wishes": [],
        "visitors": people,
        "keep_days": keep_days,
    }
