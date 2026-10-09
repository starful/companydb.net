#!/usr/bin/env python3
"""Fetch one EDINET annual report and build an English HTML analysis page."""

from __future__ import annotations

import html as htmlmod
import json
import os
import re
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

_CATALOG_LOCK = threading.Lock()

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "output" / "companies"
INDEX_PATH = ROOT / "output" / "index.html"
COMPARE_PATH = ROOT / "output" / "compare.html"
CATALOG_PATH = ROOT / "data" / "catalog.json"
FACTS_DIR = ROOT / "data" / "facts"

# Curated English IR pages (EDINET rarely carries a clean EN IR URL).
IR_EN_URLS = {
    # Japan
    "6594": "https://www.nidec.com/en/ir/",
    "7203": "https://global.toyota/en/ir/",
    "6758": "https://www.sony.com/en/SonyInfo/IR/",
    "7974": "https://www.nintendo.co.jp/ir/en/",
    "9984": "https://group.softbank/en/ir",
    "9983": "https://www.fastretailing.com/eng/ir/",
    "6861": "https://www.keyence.com/ir/",
    "8306": "https://www.mufg.jp/english/ir/",
    "9432": "https://group.ntt/en/ir/",
    "9433": "https://www.kddi.com/english/corporate/ir/",
    "7267": "https://global.honda/en/investors/",
    "6501": "https://www.hitachi.com/IR-e/",
    "6503": "https://www.mitsubishielectric.com/en/investors/",
    "6752": "https://holdings.panasonic/global/corporate/investors.html",
    "6902": "https://www.denso.com/global/en/investors/",
    "7751": "https://global.canon/en/ir/",
    "4063": "https://www.shinetsu.co.jp/en/ir/",
    "6981": "https://corporate.murata.com/en-global/ir",
    "8035": "https://www.tel.com/ir/",
    "6857": "https://www.advantest.com/investors/",
    "6367": "https://www.daikin.com/investor",
    "4519": "https://www.chugai-pharm.co.jp/english/ir/",
    "4502": "https://www.takeda.com/investors/",
    "6098": "https://recruit-holdings.com/en/ir/",
    "8411": "https://www.mizuhogroup.com/investors",
    "8316": "https://www.smfg.co.jp/english/investor/",
    "8766": "https://www.tokiomarinehd.com/en/ir/",
    "3382": "https://www.7andi.com/en/ir/",
    "2914": "https://www.jt.com/investors/",
    "8001": "https://www.itochu.co.jp/en/ir/",
    "8031": "https://www.mitsui.com/jp/en/ir/",
    "8058": "https://www.mitsubishicorp.com/jp/en/ir/",
    "7011": "https://www.mhi.com/finance",
    "7741": "https://www.hoya.com/en/investor/",
    "4568": "https://www.daiichisankyo.com/investors/",
    "6146": "https://www.disco.co.jp/eg/ir/",
    "8801": "https://www.mitsuifudosan.co.jp/english/corporate/ir/",
    "9020": "https://www.jreast.co.jp/e/investor/",
    # Korea
    "005930": "https://www.samsung.com/global/ir/",
    "000660": "https://www.skhynix.com/eng/ir/",
    "035420": "https://www.navercorp.com/en/investment",
    "035720": "https://www.kakaocorp.com/ir/main?lang=en",
    "005380": "https://www.hyundai.com/worldwide/en/company/ir",
    "000270": "https://worldwide.kia.com/int/company/ir",
    "051910": "https://www.lgchem.com/main/investors",
    "006400": "https://www.samsungsdi.com/ir/index.html",
    "066570": "https://www.lge.co.kr/global/investor",
    "373220": "https://www.lgensol.com/en/ir",
    "207940": "https://samsungbiologics.com/eng/ir",
    "068270": "https://www.celltrion.com/en-us/investment",
    "009150": "https://www.samsungsem.com/global/ir.do",
    "034730": "https://www.sk.com/en/ir",
    "259960": "https://www.krafton.com/en/ir",
    # US
    "AAPL": "https://investor.apple.com/",
    "MSFT": "https://www.microsoft.com/en-us/investor",
    "GOOGL": "https://abc.xyz/investor/",
    "AMZN": "https://www.amazon.com/ir",
    "META": "https://investor.atmeta.com/",
    "NVDA": "https://investor.nvidia.com/",
    "TSLA": "https://ir.tesla.com/",
    "JPM": "https://www.jpmorganchase.com/ir",
    "V": "https://investor.visa.com/",
    "UNH": "https://www.unitedhealthgroup.com/investors.html",
    "XOM": "https://corporate.exxonmobil.com/investors",
    "LLY": "https://investor.lilly.com/",
}

# Target universe sizes (Japan-first product + peers).
UNIVERSE_JP = [
    "6594", "7203", "6758", "7974", "9984", "9983", "6861", "8306", "9432", "9433",
    "7267", "6501", "6503", "6752", "6902", "7751", "4063", "6981", "8035", "6857",
    "6367", "4519", "4502", "6098", "8411", "8316", "8766", "3382", "2914", "8001",
    "8031", "8058", "7011", "7741", "4568", "6146", "8801", "9020",
]
UNIVERSE_KR = [
    "005930", "000660", "035420", "035720", "005380", "000270", "051910", "006400",
    "066570", "012330", "105560", "055550", "086790", "032830", "207940", "068270",
    "373220", "096770", "017670", "030200",
    "009150", "034730", "259960",
]
UNIVERSE_US = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM", "V", "UNH",
    "XOM", "LLY",
]

# Canonical English display names (filings often only carry local-language legal names).
COMPANY_EN = {
    # Japan
    "6594": "Nidec Corporation",
    "7203": "Toyota Motor Corporation",
    "6758": "Sony Group Corporation",
    "7974": "Nintendo Co., Ltd.",
    "9984": "SoftBank Group Corp.",
    "9983": "Fast Retailing Co., Ltd.",
    "6861": "Keyence Corporation",
    "8306": "Mitsubishi UFJ Financial Group, Inc.",
    "9432": "NTT, Inc.",
    "9433": "KDDI Corporation",
    "7267": "Honda Motor Co., Ltd.",
    "6501": "Hitachi, Ltd.",
    "6503": "Mitsubishi Electric Corporation",
    "6752": "Panasonic Holdings Corporation",
    "6902": "DENSO Corporation",
    "7751": "Canon Inc.",
    "4063": "Shin-Etsu Chemical Co., Ltd.",
    "6981": "Murata Manufacturing Co., Ltd.",
    "8035": "Tokyo Electron Limited",
    "6857": "Advantest Corporation",
    "6367": "Daikin Industries, Ltd.",
    "4519": "Chugai Pharmaceutical Co., Ltd.",
    "4502": "Takeda Pharmaceutical Company Limited",
    "6098": "Recruit Holdings Co., Ltd.",
    "8411": "Mizuho Financial Group, Inc.",
    "8316": "Sumitomo Mitsui Financial Group, Inc.",
    "8766": "Tokio Marine Holdings, Inc.",
    "3382": "Seven & i Holdings Co., Ltd.",
    "2914": "Japan Tobacco Inc.",
    "8001": "ITOCHU Corporation",
    "8031": "Mitsui & Co., Ltd.",
    "8058": "Mitsubishi Corporation",
    "7011": "Mitsubishi Heavy Industries, Ltd.",
    "7741": "HOYA Corporation",
    "4568": "Daiichi Sankyo Company, Limited",
    "6146": "Disco Corporation",
    "8801": "Mitsui Fudosan Co., Ltd.",
    "9020": "East Japan Railway Company",
    # Korea
    "005930": "Samsung Electronics Co., Ltd.",
    "000660": "SK hynix Inc.",
    "035420": "NAVER Corporation",
    "035720": "Kakao Corp.",
    "005380": "Hyundai Motor Company",
    "000270": "Kia Corporation",
    "051910": "LG Chem, Ltd.",
    "006400": "Samsung SDI Co., Ltd.",
    "066570": "LG Electronics Inc.",
    "012330": "Hyundai Mobis Co., Ltd.",
    "105560": "KB Financial Group Inc.",
    "055550": "Shinhan Financial Group Co., Ltd.",
    "086790": "Hana Financial Group Inc.",
    "032830": "Samsung Life Insurance Co., Ltd.",
    "207940": "Samsung Biologics Co., Ltd.",
    "068270": "Celltrion, Inc.",
    "373220": "LG Energy Solution, Ltd.",
    "096770": "SK Innovation Co., Ltd.",
    "017670": "SK Telecom Co., Ltd.",
    "030200": "KT Corporation",
    "009150": "Samsung Electro-Mechanics Co., Ltd.",
    "034730": "SK Inc.",
    "259960": "KRAFTON, Inc.",
    # US
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "GOOGL": "Alphabet Inc.",
    "AMZN": "Amazon.com, Inc.",
    "META": "Meta Platforms, Inc.",
    "NVDA": "NVIDIA Corporation",
    "TSLA": "Tesla, Inc.",
    "JPM": "JPMorgan Chase & Co.",
    "V": "Visa Inc.",
    "UNH": "UnitedHealth Group Incorporated",
    "XOM": "Exxon Mobil Corporation",
    "LLY": "Eli Lilly and Company",
}


def company_en_name(ticker: str | None, fallback: str | None = None) -> str:
    """Prefer curated English name, then caller fallback."""
    t = (ticker or "").strip()
    if t in COMPANY_EN:
        return COMPANY_EN[t]
    # JP EDINET secCode is often 5 digits with trailing 0
    if len(t) == 5 and t.endswith("0") and t[:-1] in COMPANY_EN:
        return COMPANY_EN[t[:-1]]
    return (fallback or t or "Company").strip() or "Company"


# Open DART
DART_API = "https://opendart.fss.or.kr/api"
# stock_code → corp_code (well-known issuers + data/dart_corp_codes.json)
DART_CORP_CODES = {
    "005930": "00126380",
    "000660": "00164779",
    "035420": "00266961",
    "035720": "00258801",
    "005380": "00164742",
    "000270": "00106641",
    "051910": "00356361",
    "006400": "00126362",
    "066570": "00401731",
    "012330": "00164788",
    "105560": "00688996",
    "055550": "00382199",
    "086790": "00547583",
    "032830": "00126256",
    "207940": "00877059",
    "068270": "00413046",
    "373220": "01515323",
    "096770": "00631518",
    "017670": "00159023",
    "030200": "00190321",
    "009150": "00126371",
    "034730": "00181712",
    "259960": "00760971",
}

# US ticker → zero-padded CIK
SEC_CIKS = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "GOOGL": "0001652044",
    "AMZN": "0001018724",
    "META": "0001326801",
    "NVDA": "0001045810",
    "TSLA": "0001318605",
    "JPM": "0000019617",
    "V": "0001403161",
    "UNH": "0000731766",
    # SEC ticker map remapped "XOM" to a thin Holdings shell — keep the operating issuer.
    "XOM": "0000034088",
    "LLY": "0000059478",
}
SEC_HEADERS = {
    "User-Agent": "CompanyDB/0.1 companydb@local.dev",
    "Accept-Encoding": "gzip, deflate",
}

_ACTIVE_CURRENCY = "JPY"

# Logo-aligned palette (charcoal + soft sky blue — not green).
# Source: companydb_logo.png (#303030, #90c0e0)
THEME = {
    "ink": "#2c3036",
    "paper": "#f2f4f7",
    "card": "#ffffff",
    "line": "#d5dbe3",
    "muted": "#6a7380",
    "accent": "#6a9ec4",
    "accent_deep": "#3d4f63",
    "accent_soft": "#e4eef6",
    "warn": "#b45309",
    "good": "#4a7c59",
    "bad": "#b91c1c",
}

LOGO_SRC = ROOT / "companydb_logo.png"
LOGO_ICO = ROOT / "companydb_logo.ico"
ASSETS_DIR = ROOT / "output" / "assets"


def sync_assets() -> None:
    """Copy logo / favicon into output/assets for static pages."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    if LOGO_SRC.exists():
        (ASSETS_DIR / "companydb_logo.png").write_bytes(LOGO_SRC.read_bytes())
    if LOGO_ICO.exists():
        (ASSETS_DIR / "favicon.ico").write_bytes(LOGO_ICO.read_bytes())


def css_vars() -> str:
    t = THEME
    return f"""    :root {{
      --ink: {t["ink"]};
      --paper: {t["paper"]};
      --card: {t["card"]};
      --line: {t["line"]};
      --muted: {t["muted"]};
      --accent: {t["accent"]};
      --accent-deep: {t["accent_deep"]};
      --accent-soft: {t["accent_soft"]};
      --warn: {t["warn"]};
      --good: {t["good"]};
      --bad: {t["bad"]};
    }}"""


# Keep as a plain string (not an f-string) so braces in JS stay literal.
GA_HEAD = """<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-G6QWL1SVRX"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-G6QWL1SVRX');
</script>
"""


def market_flag(market: str | None) -> str:
    """Emoji flag for market code (JP / KR / US)."""
    m = (market or "JP").upper()
    return {"JP": "🇯🇵", "KR": "🇰🇷", "US": "🇺🇸"}.get(m, "🏳️")


def market_label(market: str | None) -> str:
    m = (market or "JP").upper()
    return {"JP": "Japan", "KR": "Korea", "US": "United States"}.get(m, m)


def yahoo_symbol_for(market: str | None, ticker: str) -> str:
    m = (market or "JP").upper()
    t = (ticker or "").strip()
    if m == "JP":
        return f"{t}.T"
    if m == "KR":
        return f"{t.zfill(6)}.KS"
    return t.upper()


def fetch_market_quote(market: str | None, ticker: str) -> dict | None:
    """Best-effort delayed quote (Yahoo chart). Returns None on any failure."""
    sym = yahoo_symbol_for(market, ticker)
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
            params={"interval": "1d", "range": "5d"},
            headers={"User-Agent": "CompanyDB/0.1 companydb@local.dev"},
            timeout=12,
        )
        if r.status_code != 200:
            return None
        result = ((r.json().get("chart") or {}).get("result") or [None])[0]
        if not result:
            return None
        meta = result.get("meta") or {}
        price = meta.get("regularMarketPrice")
        if price is None:
            return None
        return {
            "symbol": sym,
            "price": float(price),
            "currency": meta.get("currency"),
            "previous_close": meta.get("previousClose"),
            "exchange": meta.get("exchangeName"),
            "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "source": "Yahoo Finance (delayed)",
        }
    except Exception:
        return None


def _stmt_line(statements: dict, *needles: str) -> dict | None:
    for key in ("income", "balance", "cashflow"):
        for line in statements.get(key) or []:
            lab = (line.get("label") or "").lower()
            if all(n.lower() in lab for n in needles):
                return line
    return None


def _first_stmt(statements: dict, options: list[tuple[str, ...]]) -> dict | None:
    for needles in options:
        hit = _stmt_line(statements, *needles)
        if hit is not None:
            return hit
    return None


def enrich_judgment(analysis: dict, *, fetch_quote: bool = True) -> dict:
    """
    Attach the closing judgment layer: takeaways, dig-deeper action,
    accounting snapshot, optional market quote / PE, hybrid-review status.
    Mutates and returns analysis.
    """
    if analysis.get("_judgment_ready"):
        return analysis

    stmts = analysis.get("statements") or {}
    one_offs = analysis.get("one_offs") or {}
    checks = analysis.get("checks") or []
    verdict = analysis.get("verdict") or "Mixed"
    headline = analysis.get("headline") or ""
    market = analysis.get("market") or "JP"
    meta = analysis.get("meta") or {}
    currency = analysis.get("currency") or (
        {"JP": "JPY", "KR": "KRW", "US": "USD"}.get(market, "JPY")
    )

    rev = _first_stmt(stmts, [("revenue",), ("net sales",), ("sales",)])
    op = _first_stmt(stmts, [("operating profit",), ("operating income",)])
    assets = _first_stmt(stmts, [("total assets",)])
    equity = _first_stmt(
        stmts,
        [
            ("owners", "equity"),
            ("stockholders", "equity"),
            ("total equity",),
            ("equity",),
        ],
    )
    eps = _first_stmt(stmts, [("basic eps",), ("eps",)])
    ocf = _first_stmt(
        stmts,
        [
            ("operating cash",),
            ("cash flows from operating",),
            ("cash flow from operating",),
            ("net cash", "operating"),
        ],
    )
    cash = _first_stmt(
        stmts,
        [
            ("cash at end",),
            ("cash & equivalents",),
            ("cash and cash",),
            ("cash and equivalents",),
        ],
    )

    def cur_of(line: dict | None) -> float | None:
        return None if line is None else line.get("cur")

    rev_c, op_c = cur_of(rev), cur_of(op)
    assets_c, equity_c = cur_of(assets), cur_of(equity)
    eps_c, ocf_c, cash_c = cur_of(eps), cur_of(ocf), cur_of(cash)

    op_margin = (op_c / rev_c) if rev_c and op_c is not None and rev_c != 0 else None
    equity_ratio = (
        (equity_c / assets_c) if assets_c and equity_c is not None and assets_c != 0 else None
    )

    imp = one_offs.get("impairment_total")
    adj = (one_offs.get("adjusted_op") or {}).get("adjusted_op")

    # Dig-deeper action
    if verdict == "Challenged":
        if imp and ocf_c is not None and ocf_c > 0:
            action = "Dig deeper"
            action_why = (
                "Reported profit looks broken, but cash stayed positive — "
                "separate the accounting reset from the operating engine."
            )
        elif op_c is not None and op_c < 0:
            action = "Park for now"
            action_why = (
                "Profitability is under pressure without a clear cash offset in this page — "
                "wait for the next cash / segment confirmation."
            )
        else:
            action = "Dig deeper"
            action_why = "Signals are stressed — confirm cash, leverage, and notes before sizing a view."
    elif verdict == "Constructive":
        action = "Worth tracking"
        action_why = (
            "Sales and operating profit moved together — keep watching margins and whether "
            "the trend persists next period."
        )
    else:
        action = "Dig deeper"
        action_why = (
            "Mixed signals — use cash flow and the balance sheet before treating the year as clean."
        )

    what = headline.strip() or "Read the statements and notes before drawing a conclusion."
    why_bits = []
    if imp is not None:
        why_bits.append(f"notes disclose a {yen(imp)} impairment / one-off charge")
    if op_margin is not None:
        why_bits.append(f"operating margin is {op_margin * 100:.1f}%")
    if ocf_c is not None and op_c is not None and op_c < 0 < ocf_c:
        why_bits.append("operating cash stayed positive despite an operating loss")
    if equity_ratio is not None:
        why_bits.append(f"equity ratio is {equity_ratio * 100:.1f}%")
    if not why_bits and checks:
        why_bits.append((checks[0].get("body") or "")[:140])
    why = (
        "; ".join(why_bits[:3]).rstrip(".") + "."
        if why_bits
        else "Key drivers sit in cash flow quality and note disclosures."
    )

    next_steps: list[str] = []
    if imp is not None:
        next_steps.append("Check which segments absorbed the impairment and whether more write-downs are possible.")
    if ocf_c is not None:
        next_steps.append("Compare operating cash flow to reported profit across the last two years.")
    next_steps.append("Open English IR for management commentary on outlook and capital allocation.")
    if adj is not None and op_c is not None:
        next_steps.append(
            f"Hold both views: reported OP {yen(op_c)} vs approx. OP before charge {yen(adj)}."
        )
    next_steps.append("Overlay peers on Compare before judging relative momentum.")
    next_steps = next_steps[:4]

    quote = None
    if fetch_quote and not analysis.get("quote"):
        quote = fetch_market_quote(market, analysis.get("ticker") or "")
    elif analysis.get("quote"):
        quote = analysis.get("quote")

    trailing_pe = None
    if quote and quote.get("price") is not None and eps_c is not None and eps_c > 0:
        # JP/KR EPS often in yen/won per share; US in USD — matches quote currency loosely.
        trailing_pe = quote["price"] / eps_c

    price_label = None
    if quote and quote.get("price") is not None:
        p = quote["price"]
        ccy = quote.get("currency") or currency
        if ccy in ("JPY", "KRW"):
            price_label = f"{ccy} {p:,.0f}"
        else:
            price_label = f"{ccy} {p:,.2f}"

    built = analysis.get("as_of") or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    analysis["judgment"] = {
        "action": action,
        "action_why": action_why,
        "what": what,
        "why": why,
        "next": next_steps,
    }
    analysis["snapshot"] = {
        "op_margin": op_margin,
        "equity_ratio": equity_ratio,
        "revenue": rev_c,
        "operating_profit": op_c,
        "eps": eps_c,
        "ocf": ocf_c,
        "cash": cash_c,
    }
    analysis["valuation"] = {
        "quote": quote,
        "price_label": price_label,
        "trailing_pe": trailing_pe,
        "note": "",
    }
    analysis["freshness"] = {
        "built": built,
        "filing_date": meta.get("date"),
        "period_end": (analysis.get("periods") or {}).get("current_end") or meta.get("periodEnd"),
        "doc_id": meta.get("docID"),
    }
    if quote:
        analysis["quote"] = quote
    analysis["_judgment_ready"] = True
    return analysis


EDINET_LIST = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
EDINET_DOC = "https://api.edinet-fsa.go.jp/api/v2/documents/{doc_id}"

# Prefer these tickers when scanning; otherwise first annual report with XBRL.
PRIORITY_SEC = ["65940", "72030", "67580", "99840", "79740", "68610", "83060", "94320"]

FACT_KEYS = [
    "NetSalesIFRS",
    "NetSales",
    "OperatingProfitLossIFRS",
    "OperatingIncome",
    "ProfitLossAttributableToOwnersOfParentIFRS",
    "ProfitLossAttributableToOwnersOfParent",
    "ProfitLossIFRS",
    "ProfitLoss",
    "AssetsIFRS",
    "Assets",
    "LiabilitiesIFRS",
    "Liabilities",
    "EquityAttributableToOwnersOfParentIFRS",
    "EquityAttributableToOwnersOfParent",
    "EquityIFRS",
    "Equity",
    "CashAndCashEquivalentsIFRS",
    "CashAndDeposits",
    "CashAndCashEquivalents",
    "NetCashProvidedByUsedInOperatingActivitiesIFRS",
    "NetCashProvidedByUsedInOperatingActivities",
    "CashFlowsFromUsedInOperatingActivitiesIFRS",
    "CashFlowsFromUsedInInvestingActivitiesIFRS",
    "CashFlowsFromUsedInFinancingActivitiesIFRS",
    "NetCashProvidedByUsedInInvestingActivitiesIFRS",
    "NetCashProvidedByUsedInInvestingActivities",
    "NetCashProvidedByUsedInFinancingActivitiesIFRS",
    "NetCashProvidedByUsedInFinancingActivities",
    "NetIncreaseDecreaseInCashAndCashEquivalentsIFRS",
    "NetIncreaseDecreaseInCashAndCashEquivalents",
    "GrossProfitIFRS",
    "GrossProfit",
    "FinanceIncomeIFRS",
    "FinanceCostsIFRS",
    "IncomeTaxExpenseIFRS",
    "IncomeTaxes",
    "TotalCurrentLiabilitiesIFRS",
    "CurrentLiabilities",
    "BorrowingsCLIFRS",
    "ShortTermLoansPayable",
    "CurrentAssetsIFRS",
    "CurrentAssets",
    "NonCurrentAssetsIFRS",
    "NoncurrentAssets",
    "BasicEarningsLossPerShareIFRS",
    "BasicEarningsLossPerShare",
    "RateOfReturnOnEquityIFRSSummaryOfBusinessResults",
    "RateOfReturnOnEquitySummaryOfBusinessResults",
    "RatioOfOwnersEquityToGrossAssetsIFRSSummaryOfBusinessResults",
    "EquityToAssetRatioSummaryOfBusinessResults",
    "NumberOfEmployees",
    "GainLossFromSalesDisposalOrImpairmentOfPropertyPlantAndEquipmentOpeCFIFRS",
    "GoodwillIFRS",
    "Goodwill",
    "SellingGeneralAndAdministrativeExpensesIFRS",
    "SellingGeneralAndAdministrativeExpenses",
]

# Prefer IFRS tags; fall back to common JGAAP / non-IFRS locals.
TAG_FALLBACKS: dict[str, list[str]] = {
    "NetSalesIFRS": ["NetSalesIFRS", "NetSales"],
    "OperatingProfitLossIFRS": ["OperatingProfitLossIFRS", "OperatingIncome"],
    "ProfitLossAttributableToOwnersOfParentIFRS": [
        "ProfitLossAttributableToOwnersOfParentIFRS",
        "ProfitLossAttributableToOwnersOfParent",
    ],
    "ProfitLossIFRS": ["ProfitLossIFRS", "ProfitLoss"],
    "AssetsIFRS": ["AssetsIFRS", "Assets"],
    "LiabilitiesIFRS": ["LiabilitiesIFRS", "Liabilities"],
    "EquityAttributableToOwnersOfParentIFRS": [
        "EquityAttributableToOwnersOfParentIFRS",
        "EquityAttributableToOwnersOfParent",
    ],
    "EquityIFRS": ["EquityIFRS", "Equity"],
    "CashAndCashEquivalentsIFRS": [
        "CashAndCashEquivalentsIFRS",
        "CashAndCashEquivalents",
        "CashAndDeposits",
    ],
    "GrossProfitIFRS": ["GrossProfitIFRS", "GrossProfit"],
    "IncomeTaxExpenseIFRS": ["IncomeTaxExpenseIFRS", "IncomeTaxes"],
    "TotalCurrentLiabilitiesIFRS": ["TotalCurrentLiabilitiesIFRS", "CurrentLiabilities"],
    "BorrowingsCLIFRS": ["BorrowingsCLIFRS", "ShortTermLoansPayable"],
    "CurrentAssetsIFRS": ["CurrentAssetsIFRS", "CurrentAssets"],
    "NonCurrentAssetsIFRS": ["NonCurrentAssetsIFRS", "NoncurrentAssets"],
    "BasicEarningsLossPerShareIFRS": [
        "BasicEarningsLossPerShareIFRS",
        "BasicEarningsLossPerShare",
    ],
    "RateOfReturnOnEquityIFRSSummaryOfBusinessResults": [
        "RateOfReturnOnEquityIFRSSummaryOfBusinessResults",
        "RateOfReturnOnEquitySummaryOfBusinessResults",
    ],
    "RatioOfOwnersEquityToGrossAssetsIFRSSummaryOfBusinessResults": [
        "RatioOfOwnersEquityToGrossAssetsIFRSSummaryOfBusinessResults",
        "EquityToAssetRatioSummaryOfBusinessResults",
    ],
    "GoodwillIFRS": ["GoodwillIFRS", "Goodwill"],
    "SellingGeneralAndAdministrativeExpensesIFRS": [
        "SellingGeneralAndAdministrativeExpensesIFRS",
        "SellingGeneralAndAdministrativeExpenses",
    ],
    "NetCashProvidedByUsedInOperatingActivitiesIFRS": [
        "NetCashProvidedByUsedInOperatingActivitiesIFRS",
        "NetCashProvidedByUsedInOperatingActivities",
        "CashFlowsFromUsedInOperatingActivitiesIFRS",
    ],
    "NetCashProvidedByUsedInInvestingActivitiesIFRS": [
        "NetCashProvidedByUsedInInvestingActivitiesIFRS",
        "NetCashProvidedByUsedInInvestingActivities",
        "CashFlowsFromUsedInInvestingActivitiesIFRS",
    ],
    "NetCashProvidedByUsedInFinancingActivitiesIFRS": [
        "NetCashProvidedByUsedInFinancingActivitiesIFRS",
        "NetCashProvidedByUsedInFinancingActivities",
        "CashFlowsFromUsedInFinancingActivitiesIFRS",
    ],
    "NetIncreaseDecreaseInCashAndCashEquivalentsIFRS": [
        "NetIncreaseDecreaseInCashAndCashEquivalentsIFRS",
        "NetIncreaseDecreaseInCashAndCashEquivalents",
    ],
}

# Statements stay readable at 2 years; key KPI trends can go longer.
MAX_YEARS = 2
TREND_YEARS = 5

CONTEXTS = {
    "CurrentYearDuration",
    "CurrentYearInstant",
    "Prior1YearDuration",
    "Prior1YearInstant",
}

# Oldest → newest context keys used for trend extraction.
TREND_DURATION_CTX = [
    "Prior4YearDuration",
    "Prior3YearDuration",
    "Prior2YearDuration",
    "Prior1YearDuration",
    "CurrentYearDuration",
]
TREND_INSTANT_CTX = [
    "Prior4YearInstant",
    "Prior3YearInstant",
    "Prior2YearInstant",
    "Prior1YearInstant",
    "CurrentYearInstant",
]

# Prefer summary-of-business-results tags (often 5 years), then fall back.
TREND_METRICS = [
    {
        "id": "revenue",
        "label": "Revenue",
        "kind": "duration",
        "tags": [
            "RevenueIFRSSummaryOfBusinessResults",
            "NetSalesSummaryOfBusinessResults",
            "NetSalesIFRS",
            "NetSales",
        ],
    },
    {
        "id": "operating_profit",
        "label": "Operating profit",
        "kind": "duration",
        "tags": [
            "OperatingProfitLossIFRSSummaryOfBusinessResults",
            "OrdinaryIncomeLossSummaryOfBusinessResults",
            "OperatingIncome",
            "OperatingProfitLossIFRS",
        ],
    },
    {
        "id": "profit_owners",
        "label": "Profit to owners",
        "kind": "duration",
        "tags": [
            "ProfitLossAttributableToOwnersOfParentIFRSSummaryOfBusinessResults",
            "NetIncomeLossSummaryOfBusinessResults",
            "ProfitLossAttributableToOwnersOfParentIFRS",
            "ProfitLossAttributableToOwnersOfParent",
        ],
    },
    {
        "id": "total_assets",
        "label": "Total assets",
        "kind": "instant",
        "tags": [
            "TotalAssetsIFRSSummaryOfBusinessResults",
            "TotalAssetsSummaryOfBusinessResults",
            "AssetsIFRS",
            "Assets",
        ],
    },
    {
        "id": "cash",
        "label": "Cash & equivalents",
        "kind": "instant",
        "tags": [
            "CashAndCashEquivalentsIFRSSummaryOfBusinessResults",
            "CashAndCashEquivalentsIFRS",
            "CashAndCashEquivalents",
            "CashAndDeposits",
        ],
    },
    {
        "id": "equity_owners",
        "label": "Owners’ equity",
        "kind": "instant",
        "tags": [
            "EquityAttributableToOwnersOfParentIFRSSummaryOfBusinessResults",
            "NetAssetsSummaryOfBusinessResults",
            "EquityAttributableToOwnersOfParentIFRS",
            "EquityAttributableToOwnersOfParent",
        ],
    },
]


def load_api_key() -> str:
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.strip().startswith("EDINET_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    key = os.environ.get("EDINET_API_KEY", "").strip()
    if not key:
        raise SystemExit("EDINET_API_KEY missing in .env")
    return key


def _normalize_sec(sec: str | None) -> str:
    s = (sec or "").strip()
    if len(s) == 4 and s.isdigit():
        return s + "0"
    return s


def find_annual_report(
    key: str,
    max_days: int = 45,
    target_sec: str | None = None,
) -> dict:
    """Scan EDINET daily lists for annual securities reports (有報) with XBRL.

    If target_sec is set (4-digit ticker or 5-digit secCode), return the newest
    match for that issuer. Otherwise prefer PRIORITY_SEC, then first found.
    """
    want = _normalize_sec(target_sec) if target_sec else None
    # Targeted searches need a longer window (many yuho land in June).
    days = max(max_days, 200) if want else max_days
    found: list[dict] = []
    for i in range(1, days + 1):
        d = (date.today() - timedelta(days=i)).isoformat()
        r = requests.get(
            EDINET_LIST,
            params={"date": d, "type": 2, "Subscription-Key": key},
            timeout=60,
        )
        r.raise_for_status()
        for x in r.json().get("results") or []:
            if (
                x.get("ordinanceCode") == "010"
                and x.get("formCode") == "030000"
                and x.get("secCode")
                and str(x.get("xbrlFlag")) == "1"
            ):
                row = {
                    "date": d,
                    "secCode": x.get("secCode"),
                    "filerName": x.get("filerName"),
                    "docID": x.get("docID"),
                    "docDescription": x.get("docDescription"),
                    "periodEnd": x.get("periodEnd"),
                    "edinetCode": x.get("edinetCode"),
                }
                if want and row["secCode"] == want:
                    return row
                found.append(row)
        if not want and len(found) >= 20:
            break

    if want:
        raise SystemExit(
            f"No annual securities report with XBRL for secCode {want} "
            f"in the last {days} days"
        )

    if not found:
        raise SystemExit("No annual securities reports with XBRL found in scan window")

    for sec in PRIORITY_SEC:
        for f in found:
            if f["secCode"] == sec:
                return f
    return found[0]


def find_annual_reports_for_secs(
    key: str,
    secs: list[str],
    max_days: int = 220,
) -> dict[str, dict]:
    """One EDINET scan → newest yuho per requested secCode."""
    want = {_normalize_sec(s) for s in secs}
    newest: dict[str, dict] = {}
    for i in range(1, max_days + 1):
        if len(newest) >= len(want):
            break
        d = (date.today() - timedelta(days=i)).isoformat()
        if i == 1 or i % 20 == 0:
            print(f"  scanning {d} ({i}/{max_days})… found {len(newest)}/{len(want)}")
        r = requests.get(
            EDINET_LIST,
            params={"date": d, "type": 2, "Subscription-Key": key},
            timeout=60,
        )
        r.raise_for_status()
        for x in r.json().get("results") or []:
            sec = x.get("secCode")
            if sec not in want:
                continue
            if not (
                x.get("ordinanceCode") == "010"
                and x.get("formCode") == "030000"
                and str(x.get("xbrlFlag")) == "1"
            ):
                continue
            # First hit is newest (we walk backward from today).
            if sec in newest:
                continue
            newest[sec] = {
                "date": d,
                "secCode": sec,
                "filerName": x.get("filerName"),
                "docID": x.get("docID"),
                "docDescription": x.get("docDescription"),
                "periodEnd": x.get("periodEnd"),
                "edinetCode": x.get("edinetCode"),
            }
    missing = sorted(want - set(newest))
    if missing:
        print(
            f"WARNING: missing annual reports for secCodes {missing} "
            f"in the last {max_days} days — continuing with {len(newest)} found"
        )
    return newest


def download_xbrl_zip(key: str, doc_id: str) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{doc_id}.zip"
    if path.exists() and path.stat().st_size > 1000:
        return path
    r = requests.get(
        EDINET_DOC.format(doc_id=doc_id),
        params={"type": 1, "Subscription-Key": key},
        timeout=180,
    )
    r.raise_for_status()
    path.write_bytes(r.content)
    return path


def _read_public_xbrl(zip_path: Path) -> str:
    with zipfile.ZipFile(zip_path) as z:
        xbrl_names = [
            n
            for n in z.namelist()
            if n.endswith(".xbrl") and "PublicDoc" in n and "AuditDoc" not in n
        ]
        if not xbrl_names:
            raise SystemExit("No PublicDoc XBRL in zip")
        return z.read(xbrl_names[0]).decode("utf-8", errors="replace")


def parse_facts(zip_path: Path) -> dict[str, dict[str, float]]:
    data = _read_public_xbrl(zip_path)
    wanted = set(FACT_KEYS)
    for metric in TREND_METRICS:
        wanted.update(metric["tags"])
    trend_contexts = set(TREND_DURATION_CTX + TREND_INSTANT_CTX)

    tag_re = re.compile(r"<([a-zA-Z0-9\-_]+:[A-Za-z0-9\-_\.]+)([^>]*)>([^<]+)</")
    facts: dict[str, dict[str, float]] = {}
    for m in tag_re.finditer(data):
        local = m.group(1).split(":")[-1]
        if local not in wanted:
            continue
        attrs = m.group(2)
        ctx_m = re.search(r'contextRef="([^"]+)"', attrs)
        context = ctx_m.group(1) if ctx_m else ""
        # Statement facts: 2-year contexts. Trend tags: up to 5-year contexts.
        if context not in CONTEXTS and context not in trend_contexts:
            continue
        if "Member" in context:
            continue
        try:
            num = float(m.group(3).strip().replace(",", ""))
        except ValueError:
            continue
        facts.setdefault(local, {})[context] = num
    return facts


def trend_year_ends(current_end: str | None) -> list[dict]:
    """Build up to TREND_YEARS labels ending at current_end (oldest → newest)."""
    if not current_end:
        return []
    ends: list[str] = []
    cur = current_end
    for _ in range(TREND_YEARS):
        ends.append(cur)
        prev = prior_period_end(cur)
        if not prev:
            break
        cur = prev
    ends = list(reversed(ends))  # oldest → newest
    return [
        {
            "id": e,
            "short": f"FY{e[:4]}" if len(e) >= 4 else e,
            "label": fiscal_year_label(e),
        }
        for e in ends
    ]


def _parse_jp_million_yen(text: str) -> float | None:
    """Parse strings like '6,321億35百万円' or '632,135' (already in 百万円)."""
    text = text.replace(",", "").replace(" ", "")
    m = re.search(r"(\d+)億(\d+)百万円", text)
    if m:
        return (int(m.group(1)) * 100 + int(m.group(2))) * 1_000_000
    m = re.search(r"(\d+)億円", text)
    if m:
        return int(m.group(1)) * 100_000_000
    m = re.search(r"(\d+)百万円", text)
    if m:
        return int(m.group(1)) * 1_000_000
    return None


def _en_one_off_label(jp: str) -> str:
    """Map common Japanese one-off phrases to short English labels."""
    rules = [
        (r"Bungie", "Bungie intangible-asset impairment"),
        (r"Pixomondo", "Pixomondo impairment / wind-down costs"),
        (r"Semiconductor Israel|持分売却にともなう損失", "Sony Semiconductor Israel disposal loss"),
        (r"ディスプレイデバイス|一部減損", "Display-device PP&E impairment"),
        (r"ソニー・ホンダ|持分法投資損失", "Sony Honda Mobility equity-method loss"),
        (r"関係会社株式評価損", "Affiliates stock valuation loss"),
        (r"パーシャル・スピンオフ", "Partial spin-off related costs"),
        (r"関係会社事業損失引当金", "Provision for affiliate business losses"),
        (r"関係会社支援損", "Affiliate support loss"),
        (r"構造改革", "Restructuring charges"),
        (r"減損", "Impairment charge"),
    ]
    for pat, en in rules:
        if re.search(pat, jp, re.I):
            return en
    cleaned = re.sub(r"^[（(－\-\s]+", "", jp).strip()
    return cleaned[:72] or "One-off charge"


def parse_one_offs(zip_path: Path, facts: dict) -> dict:
    """Extract impairment / one-off signals from XBRL facts + Japanese notes text."""
    with zipfile.ZipFile(zip_path) as z:
        chunks = []
        for n in z.namelist():
            if "PublicDoc" not in n:
                continue
            if not (n.endswith(".htm") or n.endswith(".xbrl")):
                continue
            chunks.append(z.read(n).decode("utf-8", errors="replace"))
    blob = htmlmod.unescape("\n".join(chunks))
    plain = re.sub(r"<[^>]+>", " ", blob)
    plain = re.sub(r"\s+", " ", plain)

    impairment_total = None
    # Prefer explicit group total from MD&A: 非金融資産の減損損失6,321億35百万円
    m = re.search(r"非金融資産の減損損失\s*([0-9,]+億[0-9,]*百万円)", plain)
    if m:
        impairment_total = _parse_jp_million_yen(m.group(1))
    if impairment_total is None:
        m = re.search(
            r"当連結会計年度（自\s*202[0-9]年.*?）\s*（単位：百万円）\s*報告セグメント\s*資産の種類\s*減損損失.*?合計\s*([0-9,]+)",
            plain,
        )
        if m:
            impairment_total = int(m.group(1).replace(",", "")) * 1_000_000

    # Segment impairment — prefer the explicit current-year segment rollup sentence.
    seg_map = {
        "ACIM": "Appliance, commercial & industrial (ACIM)",
        "AMEC": "Automotive motors & electronic control (AMEC)",
        "MOEN": "Motion & energy (MOEN)",
        "SPMS": "Small precision motors (SPMS)",
        "グループ会社事業": "Group company businesses",
        "機械事業": "Machinery & automation",
    }
    by_segment: list[dict] = []
    seen = set()

    # Prefer the current-year rollup sentence only (skip 前連結会計年度 figures).
    rollup_hits = re.findall(
        r"当連結会計年度において、([^。]{20,500}?を計上しています)",
        plain,
    )
    rollup_text = " ".join(rollup_hits)

    for jp_key, en_label in seg_map.items():
        amt = None
        if rollup_text:
            mm = re.search(
                rf"{re.escape(jp_key)}(?:セグメント)?(?:事業セグメント)?で(?:非金融資産の)?減損損失\s*([0-9,]+)百万円",
                rollup_text,
            )
            if mm:
                amt = int(mm.group(1).replace(",", "")) * 1_000_000
        if amt is None:
            # MD&A style: 「ACIM」…当期に非金融資産の減損損失2,988億円
            mm = re.search(
                rf"「{re.escape(jp_key)}」[^\。]{{0,120}}?"
                rf"当期に非金融資産の減損損失\s*([0-9,]+億[0-9,]*百万円|[0-9,]+億円)",
                plain,
            )
            if mm:
                amt = _parse_jp_million_yen(mm.group(1))
        if amt is not None and en_label not in seen:
            by_segment.append({"segment": en_label, "amount": amt})
            seen.add(en_label)

    by_segment.sort(key=lambda x: -(x["amount"] or 0))

    # Narrative cue (e.g. China competition for ACIM)
    drivers: list[str] = []
    if "家電用モータの中国での過当競争" in plain or "中国での過当競争" in plain:
        drivers.append(
            "Management cites intense competition in China’s appliance-motor market as a driver of the ACIM impairment."
        )
    if "のれん" in plain and impairment_total:
        drivers.append(
            "A large share of the charge relates to goodwill and related equipment written down after impairment testing."
        )

    # Sony-style MD&A bullets: （－）…減損/損失（1,201億円） — also bare 「…減損（N億円）」
    mda_items: list[dict] = []
    mda_seen_amt: set[int] = set()
    mda_patterns = [
        r"（－）\s*([^（）]{6,140}?)（([0-9,]+億[0-9,]*百万円|[0-9,]+億円)）",
        r"([A-Za-z][^（）]{0,80}?(?:減損|損失|構造改革)[^（）]{0,40}?)（([0-9,]+億円)）",
        r"((?:Bungie|Pixomondo|ディスプレイデバイス|ソニー・ホンダ)[^（）]{0,80}?)（([0-9,]+億円)）",
    ]
    for pat in mda_patterns:
        for mm in re.finditer(pat, plain):
            jp_lab = mm.group(1).strip()
            if not re.search(r"減損|損失|構造改革|売却|引当|費用", jp_lab):
                continue
            amt = _parse_jp_million_yen(mm.group(2))
            if amt is None or amt < 1_000_000_000:  # ignore < ¥1B noise
                continue
            key = int(amt)
            if key in mda_seen_amt:
                continue
            mda_seen_amt.add(key)
            kind = "impairment" if "減損" in jp_lab else "one_off"
            mda_items.append(
                {
                    "label": _en_one_off_label(jp_lab),
                    "amount": amt,
                    "nature": (
                        "Cited in MD&A as a drag on the period (impairment)"
                        if kind == "impairment"
                        else "Cited in MD&A as a drag on the period"
                    ),
                    "kind": kind,
                }
            )
    mda_items.sort(key=lambda x: -(x["amount"] or 0))

    # Parent-company special losses (特別損失) — footnote style with 百万円
    special_map = {
        "関係会社株式評価損": "Affiliates stock valuation loss",
        "パーシャル・スピンオフ関連費用": "Partial spin-off related costs",
        "関係会社事業損失引当金繰入額": "Provision for affiliate business losses",
        "関係会社支援損": "Affiliate support loss",
    }
    special_items: list[dict] = []
    special_seen: set[str] = set()
    for jp_lab, en_lab in special_map.items():
        mm = re.search(
            rf"{re.escape(jp_lab)}[^\。]{{0,80}}?([0-9,]{{3,}})百万円を特別損失",
            plain,
        )
        if not mm:
            # Table row: 関係会社株式評価損 － 100,649 (near 特別損失 block)
            mm = re.search(
                rf"{re.escape(jp_lab)}\s*[－—\-]\s*([0-9,]{{3,}})(?!\d)",
                plain,
            )
        if not mm:
            continue
        amt = int(mm.group(1).replace(",", "")) * 1_000_000
        if amt < 1_000_000_000:
            continue
        if en_lab in special_seen:
            continue
        special_seen.add(en_lab)
        special_items.append(
            {
                "label": en_lab,
                "amount": amt,
                "nature": "Parent-company special loss (特別損失)",
                "kind": "special_loss",
            }
        )
    special_total = None
    mm = re.search(r"特別損失合計\s*[－—\-]?\s*([0-9,]{3,})", plain)
    if mm:
        special_total = int(mm.group(1).replace(",", "")) * 1_000_000

    if any("Bungie" in (it.get("label") or "") for it in mda_items):
        drivers.append(
            "G&NS results were hit by a large Bungie intangible-asset impairment cited in the MD&A."
        )
    if special_items or (special_total and special_total >= 1_000_000_000):
        drivers.append(
            "The parent-company income statement also shows material special losses "
            "(valuation, spin-off, and affiliate support items)."
        )

    cf_addback = get(
        facts,
        "GainLossFromSalesDisposalOrImpairmentOfPropertyPlantAndEquipmentOpeCFIFRS",
        "CurrentYearDuration",
    )
    cf_addback_prior = get(
        facts,
        "GainLossFromSalesDisposalOrImpairmentOfPropertyPlantAndEquipmentOpeCFIFRS",
        "Prior1YearDuration",
    )
    goodwill_c = get(facts, "GoodwillIFRS", "CurrentYearInstant")
    goodwill_p = get(facts, "GoodwillIFRS", "Prior1YearInstant")
    sga_c = get(facts, "SellingGeneralAndAdministrativeExpensesIFRS", "CurrentYearDuration")
    sga_p = get(facts, "SellingGeneralAndAdministrativeExpensesIFRS", "Prior1YearDuration")

    items = []
    if impairment_total is not None:
        items.append(
            {
                "label": "Impairment of non-financial assets (group)",
                "amount": impairment_total,
                "nature": "Non-cash / largely one-off accounting charge",
            }
        )
    for seg in by_segment[:6]:
        items.append(
            {
                "label": f"└ {seg['segment']}",
                "amount": seg["amount"],
                "nature": "Segment impairment (included in group total)",
            }
        )

    # If no Nidec-style group impairment block, surface MD&A / special-loss charges.
    if impairment_total is None and not by_segment:
        merged = []
        for it in mda_items:
            merged.append(
                {
                    "label": it["label"],
                    "amount": it["amount"],
                    "nature": it["nature"],
                }
            )
        for it in special_items:
            merged.append(
                {
                    "label": it["label"],
                    "amount": it["amount"],
                    "nature": it["nature"],
                }
            )
        merged.sort(key=lambda x: -(x.get("amount") or 0))
        items.extend(merged[:10])
        if special_total is not None and special_items:
            items.append(
                {
                    "label": "Parent special losses (total)",
                    "amount": special_total,
                    "nature": "Sum of 特別損失 on the parent-company statement",
                }
            )

    segment_sum = sum(s["amount"] for s in by_segment if s.get("amount") is not None)
    n_seg = len(by_segment)
    if impairment_total is not None and n_seg >= 2:
        conf_level = "high"
    elif impairment_total is not None or n_seg >= 1:
        conf_level = "medium"
    elif len(items) >= 2:
        conf_level = "medium"
    elif items or cf_addback is not None:
        conf_level = "low"
    else:
        conf_level = "low"

    return {
        "impairment_total": impairment_total,
        "by_segment": by_segment,
        "segment_sum": segment_sum or None,
        "items": items,
        "drivers": drivers,
        "cf_addback": {"cur": cf_addback, "prior": cf_addback_prior},
        "goodwill": {"cur": goodwill_c, "prior": goodwill_p},
        "sga": {"cur": sga_c, "prior": sga_p},
        "confidence": {
            "level": conf_level,
            "label": "From notes",
        },
    }


def build_trends(facts: dict, current_end: str | None) -> dict:
    year_meta = trend_year_ends(current_end)
    # Map year index 0..n-1 onto Prior(n-1-i) / Current contexts
    n = len(year_meta)
    series = []
    for metric in TREND_METRICS:
        ctx_list = TREND_DURATION_CTX if metric["kind"] == "duration" else TREND_INSTANT_CTX
        # Take the last `n` contexts from the 5-slot lists
        ctx_slice = ctx_list[-n:] if n else []
        values: list[float | None] = []
        for ctx in ctx_slice:
            val = None
            for tag in metric["tags"]:
                val = get(facts, tag, ctx)
                if val is not None:
                    break
            values.append(val)
        if any(v is not None for v in values):
            series.append(
                {
                    "id": metric["id"],
                    "label": metric["label"],
                    "values": values,
                }
            )
    return {"years": year_meta, "series": series, "max_years": TREND_YEARS}


_SEGMENT_LABELS = {
    "SmallPrecisionMotorAndSolutions": "Small precision motors & solutions",
    "AutomotiveMotorAndElectronicControl": "Automotive motors & electronic control",
    "MotionAndEnergy": "Motion & energy",
    "ApplianceCommercialAndIndustrialMotor": "Appliance, commercial & industrial motors",
    "NidecMachineryAndAutomation": "Machinery & automation",
    "GroupCompanyBusiness": "Group company businesses",
}


def _plain_from_text_block(data: str, local_name: str) -> str:
    m = re.search(
        rf"{local_name}[^>]*>(.*?)</[a-zA-Z0-9\-_]+:{local_name}>",
        data,
        re.S,
    )
    if not m:
        return ""
    text = htmlmod.unescape(m.group(1))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&\w+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_contacts(zip_path: Path, meta: dict) -> dict:
    """Best-effort phone/email from the filing text, stamped with filing date."""
    with zipfile.ZipFile(zip_path) as z:
        chunks = []
        for n in z.namelist():
            if "PublicDoc" not in n:
                continue
            if not (n.endswith(".htm") or n.endswith(".xbrl")):
                continue
            chunks.append(z.read(n).decode("utf-8", errors="replace"))
    blob = htmlmod.unescape("\n".join(chunks))
    plain = re.sub(r"<[^>]+>", " ", blob)
    plain = re.sub(r"\s+", " ", plain)

    phones = re.findall(
        r"(?:電話番号|電話)[^\d]{0,24}(\d{2,4}-\d{2,4}-\d{3,4})",
        plain,
    )
    # Dedupe, prefer Tokyo 03- then others
    phones = list(dict.fromkeys(phones))
    phones.sort(key=lambda p: (0 if p.startswith("03-") else 1, p))
    phone = phones[0] if phones else None

    emails = re.findall(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        plain,
    )
    skip = ("example.com", ".xsd", "w3.org", "edinet")
    emails = [
        e
        for e in dict.fromkeys(emails)
        if not any(s in e.lower() for s in skip)
    ]
    email = emails[0] if emails else None

    return {
        "phone": phone,
        "email": email,
        "as_of": meta.get("date"),
        "source": "EDINET annual securities report",
    }


def parse_company_profile(zip_path: Path, meta: dict) -> dict:
    """Pull company identity / business overview from the annual report XBRL."""
    data = _read_public_xbrl(zip_path)

    en_name = None
    for pat in [
        r"CompanyNameEnglishCoverPage[^>]*>([^<]+)",
        r"CompanyNameEnglish[^>]*>([^<]+)",
        r"FilerNameInEnglishJE[^>]*>([^<]+)",
    ]:
        m = re.search(pat, data)
        if m and m.group(1).strip():
            en_name = m.group(1).strip()
            break

    business_jp = _plain_from_text_block(data, "DescriptionOfBusinessTextBlock")
    # First content sentence after the heading marker is the useful overview.
    overview_jp = ""
    if business_jp:
        cleaned = re.sub(r"^[\d一二三四五六七八九十【】\[\]事業の内容\s]+", "", business_jp)
        # Prefer the sentence that mentions 事業内容 / 製造
        parts = re.split(r"(?<=。)", cleaned)
        for p in parts:
            if "製造" in p or "販売" in p or "事業内容" in p:
                overview_jp = p.strip()
                break
        if not overview_jp and parts:
            overview_jp = parts[0].strip()

    segments: list[str] = []
    for raw in re.findall(
        r"([A-Za-z][A-Za-z0-9]+)ReportableSegment",
        data,
    ):
        key = re.sub(r"BusinessUnit$", "", raw)
        label = _SEGMENT_LABELS.get(key) or _SEGMENT_LABELS.get(raw)
        if not label:
            label = re.sub(r"([a-z])([A-Z])", r"\1 \2", key)
            label = re.sub(r"\s+", " ", label).strip()
        if label and label not in segments:
            segments.append(label)

    ticker = meta.get("secCode") or ""
    if ticker.endswith("0") and len(ticker) == 5:
        ticker = ticker[:-1]

    about_en, products = summarize_business_en(
        ticker=ticker,
        filer_name=meta.get("filerName") or "",
        en_name=en_name,
        overview_jp=overview_jp,
        segments=segments,
    )

    contacts = parse_contacts(zip_path, meta)

    return {
        "name_en": en_name,
        "overview_jp": overview_jp,
        "about_en": about_en,
        "products": products,
        "segments": segments[:8],
        "ir_en_url": IR_EN_URLS.get(ticker),
        "contacts": contacts,
    }


def summarize_business_en(
    *,
    ticker: str,
    filer_name: str,
    en_name: str | None,
    overview_jp: str,
    segments: list[str],
) -> tuple[str, list[str]]:
    """English about-blurb. Known issuers get a tight summary; others use JP cues."""
    name = en_name or filer_name or "This company"

    # Product cues from Japanese overview
    product_map = [
        ("精密小型モータ", "small precision motors"),
        ("HDD用モータ", "HDD motors"),
        ("車載", "automotive products"),
        ("家電", "appliance motors"),
        ("商業", "commercial equipment motors"),
        ("産業用", "industrial motors"),
        ("機器装置", "machinery & equipment"),
        ("工作機械", "machine tools"),
        ("電子・光学部品", "electronic & optical components"),
        ("電子部品", "electronic components"),
        ("モータ", "electric motors"),
    ]
    products: list[str] = []
    for jp, en in product_map:
        if jp in overview_jp and en not in products:
            products.append(en)

    if ticker == "6594" or "ニデック" in filer_name or (en_name and "Nidec" in en_name):
        display = "Nidec Corporation"
        about = (
            f"{display} is a Japan-based industrial group that manufactures and sells electric motors "
            "and related drive products. Its business spans small precision motors (including HDD motors), "
            "automotive products, appliance / commercial / industrial motors, machinery and machine tools, "
            "and electronic / optical components. Results are reported across multiple segments under IFRS, "
            "with a global network of consolidated subsidiaries."
        )
        products = [
            "small precision motors",
            "automotive products",
            "appliance & industrial motors",
            "machinery & machine tools",
            "electronic & optical components",
        ]
        return about, products

    if ticker == "7203" or "トヨタ自動車" in filer_name or (en_name and "Toyota" in en_name):
        return (
            "Toyota Motor Corporation is Japan’s largest automaker, designing and selling passenger cars, "
            "commercial vehicles, and mobility-related services worldwide. The group’s results are driven by "
            "vehicle unit sales, mix, and financing operations across major regions.",
            ["passenger vehicles", "commercial vehicles", "automotive financing", "mobility services"],
        )

    if ticker == "6758" or "ソニーグループ" in filer_name or (en_name and "Sony" in en_name):
        return (
            "Sony Group Corporation is a global electronics and entertainment company spanning game & network "
            "services, music, pictures, electronics products & solutions, imaging & sensing, and financial services.",
            [
                "game & network services",
                "music",
                "pictures",
                "electronics products & solutions",
                "imaging & sensing",
                "financial services",
            ],
        )

    if ticker == "7974" or "任天堂" in filer_name or (en_name and "Nintendo" in en_name):
        return (
            "Nintendo Co., Ltd. develops and sells dedicated game platforms and software, including hardware "
            "such as the Nintendo Switch family and a catalog of first-party franchises sold worldwide.",
            ["game hardware", "game software", "digital content", "character IP"],
        )

    if ticker == "9984" or "ソフトバンクグループ" in filer_name or (en_name and "SoftBank" in en_name):
        return (
            "SoftBank Group Corp. is an investment holding company with stakes in telecommunications, internet, "
            "and technology businesses, including SoftBank Corp. and major portfolio investments.",
            ["investment holdings", "telecommunications", "internet & tech portfolio"],
        )

    if products:
        product_clause = ", ".join(products[:5])
        about = (
            f"{name} is a Japanese listed company whose core business is the manufacture and sale of "
            f"{product_clause}, based on its annual securities report business description."
        )
    elif segments:
        about = (
            f"{name} is a Japanese listed company. Its reportable segments include "
            f"{', '.join(segments[:4])}."
        )
    else:
        about = (
            f"{name} is a Japanese listed company with financial statements filed on EDINET. "
            "A detailed English business summary was not auto-extracted from this filing."
        )
    return about, products


def fiscal_year_label(period_end: str | None) -> str:
    if not period_end:
        return "—"
    try:
        d = date.fromisoformat(period_end[:10])
    except ValueError:
        return period_end
    return f"FY{d.year} (ended {d.strftime('%b %d, %Y')})"


def prior_period_end(period_end: str | None) -> str | None:
    if not period_end:
        return None
    try:
        d = date.fromisoformat(period_end[:10])
    except ValueError:
        return None
    return d.replace(year=d.year - 1).isoformat()


def extract_period_ends(zip_path: Path | None, meta: dict) -> tuple[str | None, str | None]:
    """Return (current_period_end, prior_period_end), capped at MAX_YEARS."""
    current = meta.get("periodEnd")
    if zip_path and zip_path.exists():
        data = _read_public_xbrl(zip_path)
        m = re.search(r"CurrentFiscalYearEndDateDEI[^>]*>([^<]+)", data)
        if m:
            current = m.group(1).strip()[:10]
    prior = prior_period_end(current)
    return current, prior


def yen(n: float | None, digits: int = 1) -> str:
    """Format money; symbol follows _ACTIVE_CURRENCY (¥ or ₩)."""
    if n is None:
        return "—"
    abs_n = abs(n)
    sign = "-" if n < 0 else ""
    sym = {"KRW": "₩", "USD": "$", "JPY": "¥"}.get(_ACTIVE_CURRENCY, "¥")
    if abs_n >= 1e12:
        return f"{sign}{sym}{abs_n / 1e12:.{digits}f}T"
    if abs_n >= 1e9:
        return f"{sign}{sym}{abs_n / 1e9:.{digits}f}B"
    if abs_n >= 1e6:
        return f"{sign}{sym}{abs_n / 1e6:.{digits}f}M"
    return f"{sign}{sym}{abs_n:,.0f}"


def load_opendart_key() -> str:
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.strip().startswith("OPENDART_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    key = os.environ.get("OPENDART_API_KEY", "").strip()
    if not key:
        raise SystemExit("OPENDART_API_KEY missing in .env")
    return key


def _dart_amt(raw: str | None) -> float | None:
    if raw is None or raw == "" or raw == "-":
        return None
    try:
        return float(str(raw).replace(",", ""))
    except ValueError:
        return None


def dart_find_account(rows: list[dict], names: list[str], sj_div: str | None = None) -> dict | None:
    """Return first row matching account_nm (exact, then contains) and optional sj_div."""
    filtered = [r for r in rows if sj_div is None or r.get("sj_div") == sj_div]
    for name in names:
        for r in filtered:
            if r.get("account_nm") == name:
                return r
    for name in names:
        for r in filtered:
            if name in (r.get("account_nm") or ""):
                return r
    return None


def dart_fetch_company(key: str, corp_code: str) -> dict:
    r = requests.get(
        f"{DART_API}/company.json",
        params={"crtfc_key": key, "corp_code": corp_code},
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "000":
        raise SystemExit(f"DART company error: {data.get('status')} {data.get('message')}")
    return data


def dart_fetch_statements(key: str, corp_code: str, year: int) -> list[dict]:
    r = requests.get(
        f"{DART_API}/fnlttSinglAcntAll.json",
        params={
            "crtfc_key": key,
            "corp_code": corp_code,
            "bsns_year": str(year),
            "reprt_code": "11011",  # annual
            "fs_div": "CFS",
        },
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "000":
        raise RuntimeError(
            f"DART statements error {year}: {data.get('status')} {data.get('message')}"
        )
    return data.get("list") or []


def build_analysis_from_dart(
    company: dict,
    rows: list[dict],
    year: int,
    trend_by_year: dict[int, dict[str, float | None]],
) -> dict:
    """Map Open DART rows into the same analysis shape as EDINET pages."""
    global _ACTIVE_CURRENCY
    _ACTIVE_CURRENCY = "KRW"

    ticker = (company.get("stock_code") or "").strip()
    corp_name = company.get("corp_name") or company.get("stock_name") or "Company"
    en_name = company_en_name(ticker, corp_name)

    def pair(names: list[str], sj: str | None = None) -> dict:
        row = dart_find_account(rows, names, sj)
        if not row:
            return {"cur": None, "prior": None}
        return {
            "cur": _dart_amt(row.get("thstrm_amount")),
            "prior": _dart_amt(row.get("frmtrm_amount")),
        }

    sales = pair(["매출액", "수익(매출액)", "영업수익"], "IS")
    if sales["cur"] is None:
        sales = pair(["매출액", "수익(매출액)"])
    gross = pair(["매출총이익"], "IS")
    op = pair(["영업이익"], "IS")
    profit = pair(["당기순이익", "당기순이익(손실)"], "IS")
    ni = pair(
        ["지배기업의 소유주에게 귀속되는 당기순이익", "지배기업소유주지분", "당기순이익"],
        "IS",
    )
    if ni["cur"] is None:
        ni = profit
    tax = pair(["법인세비용", "법인세비용(수익)"], "IS")
    fin_cost = pair(["금융비용", "이자비용"], "IS")
    fin_inc = pair(["금융수익", "이자수익"], "IS")
    eps = pair(["기본주당이익", "기본주당순이익"], "IS")

    assets = pair(["자산총계"], "BS")
    ca = pair(["유동자산"], "BS")
    nca = pair(["비유동자산"], "BS")
    liab = pair(["부채총계"], "BS")
    cl = pair(["유동부채"], "BS")
    equity = pair(["자본총계"], "BS")
    equity_own = pair(["지배기업 소유주지분", "지배기업의 소유주에게 귀속되는 자본"], "BS")
    if equity_own["cur"] is None:
        equity_own = equity
    cash = pair(["현금및현금성자산"], "BS")
    borrow = pair(["단기차입금", "단기차입부채"], "BS")

    ocf = pair(["영업활동현금흐름", "영업활동으로 인한 현금흐름"], "CF")
    icf = pair(["투자활동현금흐름", "투자활동으로 인한 현금흐름"], "CF")
    fcf = pair(["재무활동현금흐름", "재무활동으로 인한 현금흐름"], "CF")
    cash_chg = pair(["현금및현금성자산의 순증가(감소)", "현금및현금성자산의증가(감소)"], "CF")

    current_end = f"{year}-12-31"
    prior_end = f"{year - 1}-12-31"
    years = [
        {"id": prior_end, "label": f"FY{year - 1} (ended Dec 31, {year - 1})", "key": "prior"},
        {"id": current_end, "label": f"FY{year} (ended Dec 31, {year})", "key": "cur"},
    ]

    def cos(side: str) -> float | None:
        s, g = sales[side], gross[side]
        if s is None or g is None:
            return None
        return s - g

    def ncl(side: str) -> float | None:
        t, c = liab[side], cl[side]
        if t is None or c is None:
            return None
        return t - c

    income_statement = [
        {"label": "Revenue", "prior": sales["prior"], "cur": sales["cur"]},
        {"label": "Cost of sales*", "prior": cos("prior"), "cur": cos("cur")},
        {"label": "Gross profit", "prior": gross["prior"], "cur": gross["cur"]},
        {"label": "Operating profit", "prior": op["prior"], "cur": op["cur"], "total": True},
        {"label": "Finance income", "prior": fin_inc["prior"], "cur": fin_inc["cur"]},
        {"label": "Finance costs", "prior": fin_cost["prior"], "cur": fin_cost["cur"]},
        {"label": "Income tax", "prior": tax["prior"], "cur": tax["cur"]},
        {"label": "Profit for the period", "prior": profit["prior"], "cur": profit["cur"], "total": True},
        {"label": "Profit to owners", "prior": ni["prior"], "cur": ni["cur"]},
        {"label": "Basic EPS", "prior": eps["prior"], "cur": eps["cur"], "kind": "eps"},
    ]
    balance_sheet = [
        {"label": "Cash & equivalents", "prior": cash["prior"], "cur": cash["cur"]},
        {"label": "Current assets", "prior": ca["prior"], "cur": ca["cur"]},
        {"label": "Non-current assets", "prior": nca["prior"], "cur": nca["cur"]},
        {"label": "Total assets", "prior": assets["prior"], "cur": assets["cur"], "total": True},
        {"label": "Current liabilities", "prior": cl["prior"], "cur": cl["cur"]},
        {"label": "Short-term borrowings", "prior": borrow["prior"], "cur": borrow["cur"]},
        {"label": "Non-current liabilities*", "prior": ncl("prior"), "cur": ncl("cur")},
        {"label": "Total liabilities", "prior": liab["prior"], "cur": liab["cur"], "total": True},
        {"label": "Owners’ equity", "prior": equity_own["prior"], "cur": equity_own["cur"]},
        {"label": "Total equity", "prior": equity["prior"], "cur": equity["cur"], "total": True},
    ]
    cash_flow = [
        {"label": "Operating cash flow", "prior": ocf["prior"], "cur": ocf["cur"], "total": True},
        {"label": "Investing cash flow", "prior": icf["prior"], "cur": icf["cur"]},
        {"label": "Financing cash flow", "prior": fcf["prior"], "cur": fcf["cur"]},
        {"label": "Net change in cash", "prior": cash_chg["prior"], "cur": cash_chg["cur"]},
        {"label": "Cash at end of period", "prior": cash["prior"], "cur": cash["cur"], "total": True},
    ]

    # Trends from multi-year map
    year_list = sorted(trend_by_year.keys())[-TREND_YEARS:]
    year_meta = [
        {"id": f"{y}-12-31", "short": f"FY{y}", "label": f"FY{y}"} for y in year_list
    ]

    def series_for(key: str, label: str) -> dict:
        return {
            "id": key,
            "label": label,
            "values": [trend_by_year.get(y, {}).get(key) for y in year_list],
        }

    trends = {
        "years": year_meta,
        "series": [
            series_for("revenue", "Revenue"),
            series_for("operating_profit", "Operating profit"),
            series_for("profit_owners", "Profit to owners"),
            series_for("total_assets", "Total assets"),
            series_for("cash", "Cash & equivalents"),
            series_for("equity_owners", "Owners’ equity"),
        ],
        "max_years": TREND_YEARS,
    }
    # Drop empty series
    trends["series"] = [s for s in trends["series"] if any(v is not None for v in s["values"])]

    if op["cur"] is not None and op["prior"] is not None and op["cur"] > 0 and (
        sales["cur"] and sales["prior"] and sales["cur"] > sales["prior"]
    ):
        verdict = "Constructive"
        headline = "Sales and operating profit both moved in a healthier direction."
    elif op["cur"] is not None and op["prior"] is not None and op["cur"] < 0 and op["prior"] > 0:
        verdict = "Challenged"
        headline = (
            "Revenue held up in places, but profitability collapsed into an operating loss — "
            "read this as a reset year until cash and segments confirm otherwise."
        )
    else:
        verdict = "Mixed"
        headline = (
            "The numbers send mixed signals — dig into cash flow and leverage before drawing a conclusion."
        )

    if ticker == "005930":
        about = (
            "Samsung Electronics Co., Ltd. is a Korea-based global technology group spanning "
            "semiconductors (memory and foundry), mobile communications, consumer electronics, "
            "and display-related businesses. Results are reported under K-IFRS on a consolidated basis."
        )
        products = [
            "semiconductors / memory",
            "mobile devices",
            "consumer electronics",
            "display panels",
            "network equipment",
        ]
        segments = [
            "DX (Device eXperience)",
            "DS (Device Solutions / semiconductors)",
            "SDC (Samsung Display)",
            "Harman",
        ]
    else:
        about = (
            f"{en_name} is a Korea-listed company with consolidated financial statements "
            "filed on DART (Open DART)."
        )
        products, segments = [], []

    ocf_c, ocf_p = ocf["cur"], ocf["prior"]
    if op["cur"] is not None and op["cur"] < 0 and ocf_c is not None and ocf_c > 0:
        earnings_vs_cash = (
            "Operating cash flow stayed positive while reported operating profit turned negative — "
            "suggesting large non-cash charges rather than a pure cash burn."
        )
    else:
        earnings_vs_cash = "Compare earnings and operating cash flow for earnings quality."

    liquidity = (
        f"Short-term borrowings moved from {yen(borrow['prior'])} to {yen(borrow['cur'])}."
        if borrow["cur"] is not None
        else "Watch short-term liabilities against the cash balance."
    )
    capital = (
        f"Total equity moved from {yen(equity['prior'])} to {yen(equity['cur'])}."
        if equity["cur"] is not None
        else "Capital structure: see equity vs assets on the balance sheet."
    )

    analysis_paras = [
        (
            f"On the income statement, revenue moved from {yen(sales['prior'])} to {yen(sales['cur'])} "
            f"({yoy(sales['cur'], sales['prior'])}). "
            f"Operating profit went from {yen(op['prior'])} to {yen(op['cur'])} "
            f"({yoy(op['cur'], op['prior'])})."
        ),
        (
            f"Operating cash flow was {yen(ocf_c)} (prior {yen(ocf_p)}), with cash on the balance sheet "
            f"at {yen(cash['cur'])} versus {yen(cash['prior'])}."
        ),
    ]

    rcept = None
    for r in rows:
        if r.get("rcept_no"):
            rcept = r["rcept_no"]
            break
    source_url = (
        f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept}"
        if rcept
        else "https://dart.fss.or.kr/"
    )

    return {
        "meta": {
            "date": f"{year + 1}-03-31",  # typical filing season; refined if needed
            "secCode": ticker,
            "filerName": corp_name,
            "docID": rcept or f"DART-{ticker}-{year}",
            "docDescription": f"Business report (사업보고서) FY{year}",
            "periodEnd": current_end,
            "edinetCode": company.get("corp_code"),
        },
        "ticker": ticker,
        "company_en": en_name,
        "market": "KR",
        "currency": "KRW",
        "verdict": verdict,
        "headline": headline,
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "about": {
            "summary": about,
            "products": products,
            "segments": segments,
        },
        "ir_en_url": IR_EN_URLS.get(ticker),
        "contacts": {
            "phone": company.get("phn_no") or None,
            "email": None,
            "as_of": f"{year}-12-31",
            "source": "Open DART company overview / annual report",
        },
        "periods": {
            "max_years": MAX_YEARS,
            "current_end": current_end,
            "prior_end": prior_end,
            "years": years,
            "default_focus": current_end,
        },
        "statements": {
            "income": income_statement,
            "balance": balance_sheet,
            "cashflow": cash_flow,
        },
        "trends": trends,
        "one_offs": {
            "items": [],
            "by_segment": [],
            "drivers": [],
            "confidence": {
                "level": "medium",
                "label": "From DART",
            },
        },
        "analysis_paras": analysis_paras,
        "checks": [
            {"title": "Earnings quality", "body": earnings_vs_cash},
            {"title": "Liquidity & leverage", "body": liquidity},
            {"title": "Capital buffer", "body": capital},
        ],
        "source_url": source_url,
    }


def pct(n: float | None, as_ratio: bool = True) -> str:
    if n is None:
        return "—"
    v = n * 100 if as_ratio and abs(n) <= 2 else n
    return f"{v:.1f}%"


def yoy(cur: float | None, prior: float | None) -> str:
    if cur is None or prior is None or prior == 0:
        return "—"
    change = (cur - prior) / abs(prior) * 100
    arrow = "▲" if change > 0 else "▼" if change < 0 else "→"
    return f"{arrow} {change:+.1f}%"


def get(facts: dict, tag: str, ctx: str) -> float | None:
    for candidate in TAG_FALLBACKS.get(tag, [tag]):
        bucket = facts.get(candidate) or {}
        if ctx in bucket:
            return bucket[ctx]
    return None


def _pair(facts: dict, tag: str, cur_ctx: str, prior_ctx: str) -> dict:
    return {"cur": get(facts, tag, cur_ctx), "prior": get(facts, tag, prior_ctx)}


def _first_cf(facts: dict, tags: list[str], ctx: str) -> float | None:
    for tag in tags:
        v = get(facts, tag, ctx)
        if v is not None:
            return v
    return None


def build_analysis(
    meta: dict,
    facts: dict,
    profile: dict | None = None,
    period_ends: tuple[str | None, str | None] | None = None,
    one_offs: dict | None = None,
) -> dict:
    profile = profile or {}
    one_offs = one_offs or {}
    current_end, prior_end = period_ends or (meta.get("periodEnd"), prior_period_end(meta.get("periodEnd")))
    # Enforce 2-year cap: only current + one prior label.
    years = []
    if prior_end:
        years.append({"id": prior_end, "label": fiscal_year_label(prior_end), "key": "prior"})
    if current_end:
        years.append({"id": current_end, "label": fiscal_year_label(current_end), "key": "cur"})
    years = years[-MAX_YEARS:]
    sales = _pair(facts, "NetSalesIFRS", "CurrentYearDuration", "Prior1YearDuration")
    gross = _pair(facts, "GrossProfitIFRS", "CurrentYearDuration", "Prior1YearDuration")
    op = _pair(facts, "OperatingProfitLossIFRS", "CurrentYearDuration", "Prior1YearDuration")
    fin_inc = _pair(facts, "FinanceIncomeIFRS", "CurrentYearDuration", "Prior1YearDuration")
    fin_cost = _pair(facts, "FinanceCostsIFRS", "CurrentYearDuration", "Prior1YearDuration")
    tax = _pair(facts, "IncomeTaxExpenseIFRS", "CurrentYearDuration", "Prior1YearDuration")
    profit = _pair(facts, "ProfitLossIFRS", "CurrentYearDuration", "Prior1YearDuration")
    ni = _pair(
        facts,
        "ProfitLossAttributableToOwnersOfParentIFRS",
        "CurrentYearDuration",
        "Prior1YearDuration",
    )
    eps = _pair(
        facts, "BasicEarningsLossPerShareIFRS", "CurrentYearDuration", "Prior1YearDuration"
    )

    cash = _pair(facts, "CashAndCashEquivalentsIFRS", "CurrentYearInstant", "Prior1YearInstant")
    ca = _pair(facts, "CurrentAssetsIFRS", "CurrentYearInstant", "Prior1YearInstant")
    nca = _pair(facts, "NonCurrentAssetsIFRS", "CurrentYearInstant", "Prior1YearInstant")
    assets = _pair(facts, "AssetsIFRS", "CurrentYearInstant", "Prior1YearInstant")
    cl = _pair(facts, "TotalCurrentLiabilitiesIFRS", "CurrentYearInstant", "Prior1YearInstant")
    borrow = _pair(facts, "BorrowingsCLIFRS", "CurrentYearInstant", "Prior1YearInstant")
    liab = _pair(facts, "LiabilitiesIFRS", "CurrentYearInstant", "Prior1YearInstant")
    equity_own = _pair(
        facts,
        "EquityAttributableToOwnersOfParentIFRS",
        "CurrentYearInstant",
        "Prior1YearInstant",
    )
    equity = _pair(facts, "EquityIFRS", "CurrentYearInstant", "Prior1YearInstant")

    ocf_c = _first_cf(
        facts,
        [
            "NetCashProvidedByUsedInOperatingActivitiesIFRS",
            "CashFlowsFromUsedInOperatingActivitiesIFRS",
        ],
        "CurrentYearDuration",
    )
    ocf_p = _first_cf(
        facts,
        [
            "NetCashProvidedByUsedInOperatingActivitiesIFRS",
            "CashFlowsFromUsedInOperatingActivitiesIFRS",
        ],
        "Prior1YearDuration",
    )
    icf_c = _first_cf(
        facts,
        [
            "NetCashProvidedByUsedInInvestingActivitiesIFRS",
            "CashFlowsFromUsedInInvestingActivitiesIFRS",
        ],
        "CurrentYearDuration",
    )
    icf_p = _first_cf(
        facts,
        [
            "NetCashProvidedByUsedInInvestingActivitiesIFRS",
            "CashFlowsFromUsedInInvestingActivitiesIFRS",
        ],
        "Prior1YearDuration",
    )
    fcf_c = _first_cf(
        facts,
        [
            "NetCashProvidedByUsedInFinancingActivitiesIFRS",
            "CashFlowsFromUsedInFinancingActivitiesIFRS",
        ],
        "CurrentYearDuration",
    )
    fcf_p = _first_cf(
        facts,
        [
            "NetCashProvidedByUsedInFinancingActivitiesIFRS",
            "CashFlowsFromUsedInFinancingActivitiesIFRS",
        ],
        "Prior1YearDuration",
    )
    cash_chg = _pair(
        facts,
        "NetIncreaseDecreaseInCashAndCashEquivalentsIFRS",
        "CurrentYearDuration",
        "Prior1YearDuration",
    )

    roe = _pair(
        facts,
        "RateOfReturnOnEquityIFRSSummaryOfBusinessResults",
        "CurrentYearDuration",
        "Prior1YearDuration",
    )
    equity_ratio = _pair(
        facts,
        "RatioOfOwnersEquityToGrossAssetsIFRSSummaryOfBusinessResults",
        "CurrentYearInstant",
        "Prior1YearInstant",
    )
    employees = _pair(facts, "NumberOfEmployees", "CurrentYearInstant", "Prior1YearInstant")

    def cos(side: str) -> float | None:
        s, g = sales[side], gross[side]
        if s is None or g is None:
            return None
        return s - g

    def ncl(side: str) -> float | None:
        l, c = liab[side], cl[side]
        if l is None or c is None:
            return None
        return l - c

    income_statement = [
        {"label": "Revenue", "prior": sales["prior"], "cur": sales["cur"], "total": False},
        {"label": "Cost of sales*", "prior": cos("prior"), "cur": cos("cur"), "total": False},
        {"label": "Gross profit", "prior": gross["prior"], "cur": gross["cur"], "total": True},
        {"label": "Operating profit (loss)", "prior": op["prior"], "cur": op["cur"], "total": True},
        {"label": "Finance income", "prior": fin_inc["prior"], "cur": fin_inc["cur"], "total": False},
        {"label": "Finance costs", "prior": fin_cost["prior"], "cur": fin_cost["cur"], "total": False},
        {"label": "Income tax expense", "prior": tax["prior"], "cur": tax["cur"], "total": False},
        {"label": "Profit (loss)", "prior": profit["prior"], "cur": profit["cur"], "total": True},
        {
            "label": "Profit (loss) attributable to owners",
            "prior": ni["prior"],
            "cur": ni["cur"],
            "total": True,
        },
        {"label": "Basic EPS (¥)", "prior": eps["prior"], "cur": eps["cur"], "kind": "eps"},
    ]

    balance_sheet = [
        {"label": "Cash and cash equivalents", "prior": cash["prior"], "cur": cash["cur"]},
        {"label": "Current assets", "prior": ca["prior"], "cur": ca["cur"], "total": True},
        {"label": "Non-current assets", "prior": nca["prior"], "cur": nca["cur"]},
        {"label": "Total assets", "prior": assets["prior"], "cur": assets["cur"], "total": True},
        {"label": "Short-term borrowings", "prior": borrow["prior"], "cur": borrow["cur"]},
        {"label": "Current liabilities", "prior": cl["prior"], "cur": cl["cur"], "total": True},
        {"label": "Non-current liabilities*", "prior": ncl("prior"), "cur": ncl("cur")},
        {"label": "Total liabilities", "prior": liab["prior"], "cur": liab["cur"], "total": True},
        {
            "label": "Equity attributable to owners",
            "prior": equity_own["prior"],
            "cur": equity_own["cur"],
        },
        {"label": "Total equity", "prior": equity["prior"], "cur": equity["cur"], "total": True},
    ]

    cash_flow = [
        {"label": "Cash flows from operating activities", "prior": ocf_p, "cur": ocf_c, "total": True},
        {"label": "Cash flows from investing activities", "prior": icf_p, "cur": icf_c},
        {"label": "Cash flows from financing activities", "prior": fcf_p, "cur": fcf_c},
        {
            "label": "Net increase (decrease) in cash",
            "prior": cash_chg["prior"],
            "cur": cash_chg["cur"],
            "total": True,
        },
        {
            "label": "Cash at end of period",
            "prior": cash["prior"],
            "cur": cash["cur"],
            "total": True,
        },
    ]

    imp_total = one_offs.get("impairment_total")
    # Approx. operating profit before the impairment charge (add-back).
    if imp_total is not None and op["cur"] is not None:
        one_offs = {
            **one_offs,
            "adjusted_op": {
                "reported_op": op["cur"],
                "impairment": imp_total,
                "adjusted_op": op["cur"] + imp_total,
            },
        }
    seg_sum = one_offs.get("segment_sum")
    if imp_total is not None and seg_sum is not None and seg_sum > 0:
        one_offs = {
            **one_offs,
            "coverage_note": (
                f"Segment detail covers {yen(seg_sum)} of the {yen(imp_total)} group impairment."
            ),
        }

    if imp_total is not None and op["cur"] is not None and op["cur"] < 0:
        earnings_vs_cash = (
            f"The filing discloses impairment of non-financial assets of {yen(imp_total)}. "
            f"That charge alone is larger than the operating loss of {yen(op['cur'])} in absolute terms "
            if abs(imp_total) >= abs(op["cur"])
            else f"The filing discloses impairment of non-financial assets of {yen(imp_total)}, "
            f"a major driver of the operating loss of {yen(op['cur'])} "
        )
        earnings_vs_cash += (
            f"— and operating cash flow remained {yen(ocf_c)}. "
            "This is primarily a non-cash reset of asset values, not evidence that the business stopped generating cash."
            if ocf_c is not None and ocf_c > 0
            else "Treat the earnings collapse as accounting-heavy until cash trends confirm otherwise."
        )
    elif op["cur"] is not None and op["cur"] < 0 and ocf_c is not None and ocf_c > 0:
        earnings_vs_cash = (
            "Operating cash flow stayed positive while reported operating profit turned negative — "
            "suggesting large non-cash charges (e.g. impairments) rather than a pure cash burn."
        )
    else:
        earnings_vs_cash = "Compare earnings and operating cash flow for earnings quality."
    liquidity = (
        f"Short-term borrowings jumped from {yen(borrow['prior'])} to {yen(borrow['cur'])}; "
        "watch refinancing and working-capital pressure even with a larger cash balance."
        if borrow["cur"]
        and borrow["prior"]
        and borrow["cur"] > borrow["prior"] * 2
        else "Short-term borrowing levels look more stable year over year."
    )
    capital = (
        f"Owners’ equity ratio fell from {pct(equity_ratio['prior'])} to {pct(equity_ratio['cur'])}; "
        "the balance sheet absorbed a heavy loss year."
        if equity_ratio["cur"] is not None
        and equity_ratio["prior"] is not None
        and equity_ratio["cur"] < equity_ratio["prior"]
        else "Capital structure held relatively steady."
    )

    if op["cur"] is not None and op["prior"] is not None and op["cur"] < 0 and op["prior"] > 0:
        verdict = "Challenged"
        headline = (
            "Revenue held up, but profitability collapsed into a large operating loss — "
            "this filing reads as a reset year, not a growth story."
        )
    elif (
        op["cur"] is not None
        and op["cur"] > 0
        and sales["cur"]
        and sales["prior"]
        and sales["cur"] > sales["prior"]
    ):
        verdict = "Constructive"
        headline = "Sales and operating profit both moved in a healthier direction."
    else:
        verdict = "Mixed"
        headline = (
            "The numbers send mixed signals — dig into cash flow and leverage before drawing a conclusion."
        )

    analysis_paras = [
        (
            f"On the income statement, revenue moved from {yen(sales['prior'])} to {yen(sales['cur'])} "
            f"({yoy(sales['cur'], sales['prior'])}), so the top line did not break. "
            f"Gross profit only slipped from {yen(gross['prior'])} to {yen(gross['cur'])}, "
            f"while operating profit swung from {yen(op['prior'])} to {yen(op['cur'])} — "
            "the damage is concentrated below gross profit."
        ),
    ]
    if imp_total is not None:
        top_segs = one_offs.get("by_segment") or []
        seg_bits = ", ".join(
            f"{s['segment'].split('(')[0].strip()} {yen(s['amount'])}" for s in top_segs[:3]
        )
        para = (
            f"The notes quantify the one-off: impairment of non-financial assets totaled {yen(imp_total)} "
            f"in the latest year"
        )
        if seg_bits:
            para += f", led by {seg_bits}"
        adj = (one_offs.get("adjusted_op") or {}).get("adjusted_op")
        if adj is not None:
            para += (
                f". Adding the charge back, approximate operating profit before impairment would be "
                f"{yen(adj)} versus reported {yen(op['cur'])}"
            )
        para += (
            ". Management books these charges mainly in SG&A; they reverse into the cash-flow statement "
            "as a large non-cash add-back, which is why operating cash can stay positive while earnings look catastrophic."
        )
        analysis_paras.append(para)
        for d in one_offs.get("drivers") or []:
            analysis_paras.append(d)
    elif one_offs.get("items"):
        top = one_offs["items"][:3]
        bits = ", ".join(
            f"{it['label']} {yen(it.get('amount'))}" for it in top if it.get("amount") is not None
        )
        analysis_paras.append(
            f"The notes flag material one-offs this year"
            + (f", including {bits}" if bits else "")
            + ". Treat these as discrete charges when reading the earnings move."
        )
        for d in one_offs.get("drivers") or []:
            analysis_paras.append(d)
        analysis_paras.append(
            f"Operating cash flow was {yen(ocf_c)} (prior {yen(ocf_p)}), with cash on the balance sheet "
            f"at {yen(cash['cur'])} versus {yen(cash['prior'])}."
        )
    else:
        analysis_paras.append(
            f"Cash tells a different story than earnings. Operating cash flow was still "
            f"{yen(ocf_c)} (prior {yen(ocf_p)}), and cash on the balance sheet rose to {yen(cash['cur'])} "
            f"from {yen(cash['prior'])}. When profits collapse but operating cash stays positive, "
            "read the notes for impairments and other non-cash charges before assuming the business "
            "stopped generating cash."
        )

    gw = one_offs.get("goodwill") or {}
    if gw.get("cur") is not None and gw.get("prior") is not None and gw["cur"] < gw["prior"]:
        analysis_paras.append(
            f"Goodwill on the balance sheet fell from {yen(gw['prior'])} to {yen(gw['cur'])}, "
            "consistent with heavy write-downs of past acquisitions’ carrying values."
        )

    analysis_paras.append(
        f"The balance sheet got heavier on leverage. Total liabilities rose to {yen(liab['cur'])} "
        f"while owners’ equity fell to {yen(equity_own['cur'])}. ROE moved from "
        f"{pct(roe['prior'])} to {pct(roe['cur'])}, and the equity ratio from "
        f"{pct(equity_ratio['prior'])} to {pct(equity_ratio['cur'])}. "
        + (
            f"Employee count is {employees['cur']:,.0f} vs {employees['prior']:,.0f} a year earlier."
            if employees["cur"] is not None and employees["prior"] is not None
            else ""
        )
    )

    if op["cur"] is not None and op["prior"] is not None and op["cur"] < 0 and op["prior"] > 0:
        if imp_total is not None:
            headline = (
                f"Revenue held, but a {yen(imp_total)} impairment charge turned operating profit deeply red — "
                "read this year as an accounting reset, then judge the underlying engine on cash and segments."
            )

    ticker = meta.get("secCode") or ""
    if ticker.endswith("0") and len(ticker) == 5:
        ticker = ticker[:-1]

    company_en = company_en_name(
        ticker,
        profile.get("name_en") or meta.get("filerName"),
    )

    return {
        "meta": meta,
        "ticker": ticker,
        "company_en": company_en,
        "market": "JP",
        "verdict": verdict,
        "headline": headline,
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "about": {
            "summary": profile.get("about_en")
            or f"{company_en} is a Japanese listed company with EDINET financial filings.",
            "products": profile.get("products") or [],
            "segments": profile.get("segments") or [],
        },
        "ir_en_url": profile.get("ir_en_url") or IR_EN_URLS.get(ticker),
        "contacts": profile.get("contacts")
        or {
            "phone": None,
            "email": None,
            "as_of": meta.get("date"),
            "source": "EDINET annual securities report",
        },
        "periods": {
            "max_years": MAX_YEARS,
            "current_end": current_end,
            "prior_end": prior_end,
            "years": years,
            "default_focus": years[-1]["id"] if years else None,
        },
        "statements": {
            "income": income_statement,
            "balance": balance_sheet,
            "cashflow": cash_flow,
        },
        "trends": build_trends(facts, current_end),
        "one_offs": one_offs,
        "analysis_paras": analysis_paras,
        "checks": [
            {"title": "Earnings quality", "body": earnings_vs_cash},
            {"title": "Liquidity & leverage", "body": liquidity},
            {"title": "Capital buffer", "body": capital},
        ],
        "source_url": f"https://disclosure2.edinet-fsa.go.jp/weee0010.aspx?docid={meta['docID']}",
    }


def reaction_panel_html(slug: str) -> str:
    """Like/dislike panel — talks to Flask /api/reactions (same pattern as okcaddie)."""
    slug_js = json.dumps(slug)
    return f"""
    <section class="reaction-panel" aria-label="Page feedback">
      <p class="reaction-panel-title">Was this page helpful?</p>
      <div class="reaction-container">
        <button id="btn-like" class="reaction-btn" type="button" aria-label="Like">
          <span class="ico" aria-hidden="true">👍</span>
          <span id="count-like">0</span>
        </button>
        <button id="btn-dislike" class="reaction-btn" type="button" aria-label="Dislike">
          <span class="ico" aria-hidden="true">👎</span>
          <span id="count-dislike">0</span>
        </button>
      </div>
    </section>
    <script>
    (function () {{
      const itemSlug = {slug_js};
      const btnLike = document.getElementById("btn-like");
      const btnDislike = document.getElementById("btn-dislike");
      if (!btnLike || !btnDislike) return;

      async function loadCounts() {{
        try {{
          const res = await fetch("/api/reactions/" + encodeURIComponent(itemSlug));
          const data = await res.json();
          document.getElementById("count-like").textContent = data.likes || 0;
          document.getElementById("count-dislike").textContent = data.dislikes || 0;
          const mine = localStorage.getItem("reaction_" + itemSlug);
          if (mine === "like") btnLike.classList.add("active-like");
          if (mine === "dislike") btnDislike.classList.add("active-dislike");
        }} catch (e) {{
          /* offline / file:// — keep zeros */
        }}
      }}

      async function toggleReaction(type) {{
        btnLike.style.pointerEvents = "none";
        btnDislike.style.pointerEvents = "none";
        try {{
          const res = await fetch("/api/" + type + "/" + encodeURIComponent(itemSlug), {{
            method: "POST",
          }});
          const data = await res.json();
          if (data.status === "success") {{
            document.getElementById("count-like").textContent = data.likes;
            document.getElementById("count-dislike").textContent = data.dislikes;
            btnLike.classList.remove("active-like");
            btnDislike.classList.remove("active-dislike");
            localStorage.removeItem("reaction_" + itemSlug);
            if (data.current_type === "like") {{
              btnLike.classList.add("active-like");
              localStorage.setItem("reaction_" + itemSlug, "like");
            }} else if (data.current_type === "dislike") {{
              btnDislike.classList.add("active-dislike");
              localStorage.setItem("reaction_" + itemSlug, "dislike");
            }}
          }}
        }} catch (e) {{
          console.error("Failed to post reaction:", e);
        }} finally {{
          btnLike.style.pointerEvents = "auto";
          btnDislike.style.pointerEvents = "auto";
        }}
      }}

      btnLike.addEventListener("click", () => toggleReaction("like"));
      btnDislike.addEventListener("click", () => toggleReaction("dislike"));
      loadCounts();
    }})();
    </script>
"""


def render_html(analysis: dict, *, fetch_quote: bool = True) -> str:
    global _ACTIVE_CURRENCY
    enrich_judgment(analysis, fetch_quote=fetch_quote)
    _ACTIVE_CURRENCY = analysis.get("currency") or "JPY"

    meta = analysis["meta"]
    stmts = analysis["statements"]
    periods = analysis.get("periods") or {}
    years = periods.get("years") or []
    prior_label = next((y["label"] for y in years if y["key"] == "prior"), "Prior year")
    cur_label = next((y["label"] for y in years if y["key"] == "cur"), "Latest year")
    default_focus = periods.get("default_focus") or (years[-1]["id"] if years else "")
    market = analysis.get("market") or "JP"
    filing_system = {"KR": "DART", "US": "SEC EDGAR", "JP": "EDINET"}.get(market, "EDINET")
    accounting = {"KR": "K-IFRS", "US": "US GAAP", "JP": "IFRS"}.get(market, "IFRS")
    currency_word = {"KR": "won", "US": "dollars", "JP": "yen"}.get(market, "yen")
    verdict_cls = (analysis.get("verdict") or "Mixed").lower()

    judgment = analysis.get("judgment") or {}
    snapshot = analysis.get("snapshot") or {}
    valuation = analysis.get("valuation") or {}
    freshness = analysis.get("freshness") or {}
    action = judgment.get("action") or "Dig deeper"
    action_cls = {
        "Dig deeper": "dig",
        "Worth tracking": "track",
        "Park for now": "park",
    }.get(action, "dig")
    next_html = "".join(
        f"<li>{htmlmod.escape(s)}</li>" for s in (judgment.get("next") or [])
    )
    op_m = snapshot.get("op_margin")
    eq_r = snapshot.get("equity_ratio")
    pe = valuation.get("trailing_pe")
    price_label = valuation.get("price_label")
    snap_cells = [
        ("Action", htmlmod.escape(action), action_cls),
        (
            "OP margin",
            f"{op_m * 100:.1f}%" if op_m is not None else "—",
            "",
        ),
        (
            "Equity ratio",
            f"{eq_r * 100:.1f}%" if eq_r is not None else "—",
            "",
        ),
        (
            "Last price",
            htmlmod.escape(price_label) if price_label else "—",
            "muted" if not price_label else "",
        ),
        (
            "Trailing P/E",
            f"{pe:.1f}×" if pe is not None else "—",
            "muted" if pe is None else "",
        ),
    ]
    snap_html = "".join(
        f'<div class="snap-cell {cls}"><span>{lab}</span><strong>{val}</strong></div>'
        for lab, val, cls in snap_cells
    )
    fresh_bits = []
    if freshness.get("filing_date"):
        fresh_bits.append(f"Filed {htmlmod.escape(str(freshness['filing_date']))}")
    if freshness.get("period_end"):
        fresh_bits.append(f"Period end {htmlmod.escape(str(freshness['period_end']))}")
    fresh_html = " · ".join(fresh_bits)

    def fmt_cell(val, kind: str = "yen") -> str:
        if kind == "eps":
            return f"{val:,.2f}" if val is not None else "—"
        return yen(val)

    def stmt_rows(lines: list[dict]) -> str:
        parts = []
        for line in lines:
            kind = line.get("kind", "yen")
            prior_s = fmt_cell(line.get("prior"), kind)
            cur_s = fmt_cell(line.get("cur"), kind)
            cls = "total" if line.get("total") else ""
            prior_neg = " neg" if line.get("prior") is not None and line["prior"] < 0 else ""
            cur_neg = " neg" if line.get("cur") is not None and line["cur"] < 0 else ""
            parts.append(
                f'<tr class="{cls}"><th>{htmlmod.escape(line["label"])}</th>'
                f'<td class="col-prior{prior_neg}">{prior_s}</td>'
                f'<td class="col-cur{cur_neg}">{cur_s}</td></tr>'
            )
        return "\n".join(parts)

    def stmt_table(title: str, lines: list[dict], note: str = "") -> str:
        note_html = f'<p class="stmt-note">{note}</p>' if note else ""
        return f"""
      <div class="stmt">
        <h3>{title}</h3>
        {note_html}
        <table class="stmt-table">
          <thead>
            <tr>
              <th>Account</th>
              <th class="col-prior-h">{htmlmod.escape(prior_label)}</th>
              <th class="col-cur-h focus">{htmlmod.escape(cur_label)}</th>
            </tr>
          </thead>
          <tbody>
            {stmt_rows(lines)}
          </tbody>
        </table>
      </div>"""

    checks_html = "\n".join(
        f'<article class="check"><h3>{c["title"]}</h3><p>{c["body"]}</p></article>'
        for c in analysis["checks"]
    )
    paras_html = "\n".join(f"<p>{p}</p>" for p in analysis["analysis_paras"])
    about = analysis.get("about") or {}
    chips = about.get("products") or about.get("segments") or []
    chips_html = ""
    if chips:
        chips_html = (
            '<ul class="chips">'
            + "".join(f"<li>{htmlmod.escape(c)}</li>" for c in chips[:8])
            + "</ul>"
        )
    segments = about.get("segments") or []
    segments_html = ""
    if segments:
        segments_html = (
            '<p class="segments"><span>Segments</span> '
            + " · ".join(htmlmod.escape(s) for s in segments[:6])
            + "</p>"
        )

    ir_url = analysis.get("ir_en_url")
    contacts = analysis.get("contacts") or {}
    link_bits = []
    if ir_url:
        link_bits.append(
            f'<a class="ext-link" href="{htmlmod.escape(ir_url)}" '
            f'target="_blank" rel="noopener noreferrer">English IR</a>'
        )
    link_bits.append('<a class="ext-link" href="../compare.html">Compare trends</a>')
    contact_bits = []
    if contacts.get("phone"):
        contact_bits.append(f"Tel {htmlmod.escape(contacts['phone'])}")
    if contacts.get("email"):
        contact_bits.append(f"Email {htmlmod.escape(contacts['email'])}")
    as_of = contacts.get("as_of") or meta.get("date")
    contact_line = ""
    if contact_bits:
        contact_line = (
            '<p class="contact-line">'
            + " · ".join(contact_bits)
            + (
                f' <span class="as-of">· As of filing date {htmlmod.escape(as_of)}</span>'
                if as_of
                else ""
            )
            + "</p>"
        )
    elif as_of:
        contact_line = (
            f'<p class="contact-line muted">No phone/email found in this filing '
            f'<span class="as-of">· Filing date {htmlmod.escape(as_of)}</span></p>'
        )
    company_links_html = (
        f'<div class="company-links">{"".join(link_bits)}{contact_line}</div>'
    )

    options_html = "\n".join(
        f'<option value="{htmlmod.escape(y["id"])}"'
        f'{" selected" if y["id"] == default_focus else ""}>'
        f'{htmlmod.escape(y["label"])}</option>'
        for y in years
    )
    years_json = json.dumps(years, ensure_ascii=False).replace("</", "<\\/")

    def pnl_amt_cell(val: float | None, *, as_charge: bool = False) -> str:
        """Amount cell: loss/charge → red, profit → green."""
        if val is None:
            return '<td class="amt">—</td>'
        shown = -abs(val) if as_charge else val
        if shown < 0:
            cls = "amt loss"
        elif shown > 0:
            cls = "amt profit"
        else:
            cls = "amt"
        return f'<td class="{cls}">{yen(shown)}</td>'

    one_offs = analysis.get("one_offs") or {}
    one_off_rows = []
    for item in one_offs.get("items") or []:
        # Impairment / one-off charges are losses even when stored as positive magnitudes.
        one_off_rows.append(
            "<tr>"
            f'<th>{htmlmod.escape(item["label"])}</th>'
            f'{pnl_amt_cell(item.get("amount"), as_charge=True)}'
            f'<td class="nature">{htmlmod.escape(item.get("nature") or "")}</td>'
            "</tr>"
        )
    cf_ab = one_offs.get("cf_addback") or {}
    if cf_ab.get("cur") is not None:
        one_off_rows.append(
            "<tr class='total'>"
            "<th>CF add-back: disposal / impairment of PP&E</th>"
            f'{pnl_amt_cell(cf_ab.get("cur"))}'
            "<td class='nature'>Non-cash add-back in operating cash flow "
            f"(prior year {yen(cf_ab.get('prior'))})</td>"
            "</tr>"
        )
    adj_op = one_offs.get("adjusted_op") or {}
    adj_rows = []
    if adj_op.get("adjusted_op") is not None:
        rep = adj_op.get("reported_op")
        adj_val = adj_op.get("adjusted_op")
        adj_rows = [
            "<tr>"
            "<th>Reported operating profit</th>"
            f"{pnl_amt_cell(rep)}"
            '<td class="nature">As stated on the income statement</td>'
            "</tr>",
            "<tr>"
            "<th>Add back: impairment charge</th>"
            f'{pnl_amt_cell(adj_op.get("impairment"))}'
            '<td class="nature">Non-cash charge included in reported OP</td>'
            "</tr>",
            "<tr class='total'>"
            "<th>Approx. OP before impairment</th>"
            f"{pnl_amt_cell(adj_val)}"
            '<td class="nature">Approx. add-back</td>'
            "</tr>",
        ]
    coverage = one_offs.get("coverage_note") or ""
    coverage_html = (
        f'<p class="coverage-note">{htmlmod.escape(coverage)}</p>' if coverage else ""
    )
    adj_table = ""
    if adj_rows:
        adj_table = f"""
        <h3 class="subhead">Approx. OP before impairment</h3>
        <table>
          <thead>
            <tr><th>Item</th><th>Amount</th><th>Note</th></tr>
          </thead>
          <tbody>
            {"".join(adj_rows)}
          </tbody>
        </table>"""
    if one_off_rows or adj_rows:
        body = f"""
        {coverage_html}
        <table>
          <thead>
            <tr><th>Item</th><th>Amount</th><th>Note</th></tr>
          </thead>
          <tbody>
            {"".join(one_off_rows)}
          </tbody>
        </table>
        {adj_table}"""
    else:
        body = (
            '<p class="oneoff-empty">No material one-offs extracted from this filing.</p>'
        )
    one_offs_html = f"""
      <div class="stmt oneoff-stmt">
        <div class="oneoff-head">
          <h3>From the notes</h3>
        </div>
        {body}
      </div>"""

    trends = analysis.get("trends") or {"years": [], "series": []}
    trend_years = trends.get("years") or []
    trend_headers = "".join(
        f"<th>{htmlmod.escape(y.get('short') or y.get('id') or '')}</th>" for y in trend_years
    )

    def sparkline(vals: list) -> str:
        nums = [v for v in vals if v is not None]
        if len(nums) < 2:
            return '<span class="spark empty">—</span>'
        lo, hi = min(nums), max(nums)
        span = hi - lo if hi != lo else 1.0
        w, h, pad = 72, 22, 2
        pts = []
        indexed = [(i, v) for i, v in enumerate(vals) if v is not None]
        for i, v in indexed:
            x = pad + (w - 2 * pad) * (i / max(len(vals) - 1, 1))
            y = h - pad - (h - 2 * pad) * ((v - lo) / span)
            pts.append(f"{x:.1f},{y:.1f}")
        last_neg = indexed[-1][1] < 0
        color = "#9f1239" if last_neg else "#6a9ec4"
        return (
            f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'aria-hidden="true"><polyline fill="none" stroke="{color}" '
            f'stroke-width="1.8" points="{" ".join(pts)}"/></svg>'
        )

    trend_rows = []
    for row in trends.get("series") or []:
        cells = []
        for v in row.get("values") or []:
            neg = " neg" if v is not None and v < 0 else ""
            cells.append(f'<td class="{neg}">{yen(v)}</td>')
        # pad if short
        while len(cells) < len(trend_years):
            cells.insert(0, "<td>—</td>")
        trend_rows.append(
            "<tr>"
            f'<th>{htmlmod.escape(row["label"])}</th>'
            f'<td class="spark-cell">{sparkline(row.get("values") or [])}</td>'
            + "".join(cells)
            + "</tr>"
        )
    trends_table = ""
    if trend_rows and trend_years:
        trends_table = f"""
      <div class="stmt trend-stmt">
        <h3>Key metrics</h3>
        <table class="trend-table">
          <thead>
            <tr>
              <th>Metric</th>
              <th>Trend</th>
              {trend_headers}
            </tr>
          </thead>
          <tbody>
            {"".join(trend_rows)}
          </tbody>
        </table>
      </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
{GA_HEAD}  <title>{analysis["company_en"]} ({analysis["ticker"]}) — CompanyDB</title>
  <meta name="description" content="Financial statements and plain-English analysis for {analysis["company_en"]}." />
  <link rel="icon" href="../assets/favicon.ico" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Libre+Baskerville:wght@400;700&display=swap" rel="stylesheet" />
  <style>
{css_vars()}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", system-ui, sans-serif;
      color: var(--ink);
      background:
        radial-gradient(1200px 600px at 10% -10%, #dce8f2 0%, transparent 55%),
        radial-gradient(900px 500px at 100% 0%, #ebe4d8 0%, transparent 50%),
        var(--paper);
      line-height: 1.55;
    }}
    .wrap {{ max-width: 880px; margin: 0 auto; padding: 2rem 1.25rem 4rem; }}
    .topnav {{
      display: flex; flex-wrap: wrap; align-items: center;
      justify-content: space-between; gap: 0.5rem 1rem;
      margin-bottom: 0.75rem;
    }}
    .brand {{
      display: inline-flex;
      align-items: center;
      text-decoration: none;
    }}
    .brand-logo-sm {{
      display: block;
      height: 40px;
      width: auto;
    }}
    .nav-link {{
      font-size: 0.85rem; color: var(--accent-deep); text-decoration: none; font-weight: 500;
    }}
    .nav-link:hover {{ text-decoration: underline; text-underline-offset: 0.2em; }}
    h1 {{
      font-family: "Libre Baskerville", Georgia, serif;
      font-size: clamp(1.75rem, 4vw, 2.4rem);
      line-height: 1.15; margin: 0 0 0.35rem;
    }}
    .sub {{ color: var(--muted); margin: 0 0 1.25rem; }}
    .market-inline {{
      color: var(--accent-deep);
      font-weight: 600;
      white-space: nowrap;
    }}
    .company-links {{
      margin-top: 1rem;
      padding-top: 0.85rem;
      border-top: 1px solid var(--line);
      display: flex;
      flex-direction: column;
      gap: 0.45rem;
    }}
    .company-links .ext-link {{
      display: inline-block;
      margin-right: 0.85rem;
      color: var(--accent-deep);
      font-weight: 600;
      font-size: 0.88rem;
      text-decoration: none;
    }}
    .company-links .ext-link:hover {{
      text-decoration: underline;
      text-underline-offset: 0.2em;
    }}
    .contact-line {{
      margin: 0;
      font-size: 0.82rem;
      color: var(--ink);
    }}
    .contact-line.muted {{ color: var(--muted); }}
    .contact-line .as-of {{ color: var(--muted); }}
    .meta-line {{
      display: flex; flex-wrap: wrap; gap: 0.5rem 1.1rem;
      font-size: 0.85rem; color: var(--muted); margin-bottom: 0.65rem;
    }}
    .fresh-strip {{
      font-size: 0.78rem; color: var(--muted); margin: 0 0 1rem;
    }}
    .judgment {{
      background:
        linear-gradient(165deg, rgba(106, 158, 196, 0.14) 0%, transparent 50%),
        var(--card);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 1.2rem 1.25rem 1.15rem;
      margin-bottom: 1.15rem;
      animation: rise 0.55s ease both;
    }}
    .judgment-top {{
      display: flex; flex-wrap: wrap; align-items: center;
      justify-content: space-between; gap: 0.55rem 1rem;
      margin-bottom: 0.85rem;
    }}
    .judgment-kicker {{
      margin: 0;
      font-size: 0.72rem; letter-spacing: 0.12em; text-transform: uppercase;
      color: var(--accent-deep); font-weight: 600;
    }}
    .action-badge {{
      display: inline-block; padding: 0.35rem 0.75rem; border-radius: 999px;
      font-size: 0.75rem; font-weight: 700; letter-spacing: 0.03em;
      border: 1px solid var(--line); background: #eef2f6;
    }}
    .action-badge.dig {{ color: var(--accent-deep); border-color: #9bb8d0; background: #e8f1f8; }}
    .action-badge.track {{ color: var(--good); border-color: #86efac; background: #f0fdf4; }}
    .action-badge.park {{ color: var(--warn); border-color: #fdba74; background: #fff7ed; }}
    .judgment h2 {{
      font-family: "Libre Baskerville", Georgia, serif;
      font-size: 1.2rem; margin: 0 0 0.35rem; line-height: 1.35;
    }}
    .judgment .why {{ margin: 0 0 0.9rem; color: var(--muted); font-size: 0.95rem; }}
    .judgment .action-why {{
      margin: 0 0 1rem; font-size: 0.9rem; color: var(--ink);
    }}
    .judgment h3 {{
      margin: 0 0 0.4rem; font-size: 0.78rem; letter-spacing: 0.06em;
      text-transform: uppercase; color: var(--accent);
    }}
    .judgment ol {{
      margin: 0; padding-left: 1.15rem; font-size: 0.9rem;
    }}
    .judgment ol li {{ margin: 0 0 0.35rem; }}
    .snap-row {{
      display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 0.65rem; margin: 1.1rem 0 0.85rem;
    }}
    @media (min-width: 720px) {{
      .snap-row {{ grid-template-columns: repeat(5, minmax(0, 1fr)); }}
    }}
    .snap-cell {{
      border-top: 1px solid var(--line); padding-top: 0.45rem;
    }}
    .snap-cell span {{
      display: block; font-size: 0.68rem; letter-spacing: 0.04em;
      text-transform: uppercase; color: var(--muted); margin-bottom: 0.2rem;
    }}
    .snap-cell strong {{
      font-size: 0.95rem; font-variant-numeric: tabular-nums;
    }}
    .snap-cell.muted strong {{ color: var(--muted); font-weight: 500; font-size: 0.85rem; }}
    .snap-cell.dig strong {{ color: var(--accent-deep); }}
    .snap-cell.track strong {{ color: var(--good); }}
    .snap-cell.park strong {{ color: var(--warn); }}
    .period-bar {{
      display: flex; flex-wrap: wrap; align-items: center; gap: 0.65rem 1rem;
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 0.85rem 1.1rem;
      margin-bottom: 1.25rem;
      animation: rise 0.5s ease both;
    }}
    .period-bar label {{
      font-size: 0.8rem; font-weight: 600; color: var(--accent);
      letter-spacing: 0.04em; text-transform: uppercase;
    }}
    .period-bar select {{
      font: inherit; font-size: 0.95rem;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 0.45rem 0.7rem;
      background: #ffffff;
      color: var(--ink);
      min-width: min(100%, 280px);
    }}
    .period-bar .hint {{
      font-size: 0.8rem; color: var(--muted);
    }}
    th.focus, td.focus-col {{
      background: #e8f1f8;
    }}
    .about {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 1.15rem 1.25rem 1.05rem;
      margin-bottom: 0.25rem;
      animation: rise 0.55s ease both;
    }}
    .about h2 {{
      font-family: "Libre Baskerville", Georgia, serif;
      font-size: 1.15rem; margin: 0 0 0.55rem;
    }}
    .about > p {{ margin: 0; max-width: 48rem; }}
    .chips {{
      list-style: none; padding: 0; margin: 0.85rem 0 0;
      display: flex; flex-wrap: wrap; gap: 0.45rem;
    }}
    .chips li {{
      font-size: 0.78rem; padding: 0.28rem 0.65rem;
      border: 1px solid var(--line); border-radius: 999px;
      background: #eef2f6; color: var(--ink);
    }}
    .segments {{
      margin: 0.75rem 0 0; font-size: 0.82rem; color: var(--muted);
    }}
    .segments span {{
      color: var(--accent); font-weight: 600; margin-right: 0.35rem;
    }}
    .badge {{
      display: inline-block; padding: 0.3rem 0.7rem; border-radius: 999px;
      font-size: 0.72rem; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase;
      border: 1px solid var(--line); background: var(--card);
    }}
    .badge.challenged {{ color: var(--warn); border-color: #fdba74; background: #fff7ed; }}
    .badge.constructive {{ color: var(--good); border-color: #86efac; background: #f0fdf4; }}
    .badge.mixed {{ color: var(--muted); }}
    section {{ margin-top: 2.25rem; animation: rise 0.65s ease both; }}
    section > h2 {{
      font-family: "Libre Baskerville", Georgia, serif;
      font-size: 1.35rem; margin: 0 0 0.35rem;
    }}
    .section-sub {{ color: var(--muted); margin: 0 0 1.1rem; font-size: 0.95rem; }}
    .stmt {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 1rem 1rem 0.35rem;
      margin-bottom: 1rem;
    }}
    .stmt h3 {{
      margin: 0 0 0.65rem;
      font-size: 0.95rem;
      font-weight: 600;
      letter-spacing: 0.02em;
    }}
    .stmt-note {{ margin: -0.35rem 0 0.65rem; font-size: 0.78rem; color: var(--muted); }}
    table {{
      width: 100%; border-collapse: collapse;
      font-variant-numeric: tabular-nums;
    }}
    th, td {{
      padding: 0.45rem 0.2rem;
      text-align: right;
      border-bottom: 1px solid #ebe6da;
      font-size: 0.92rem;
    }}
    th:first-child, td:first-child {{ text-align: left; font-weight: 400; }}
    thead th {{
      font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em;
      color: var(--muted); border-bottom: 1px solid var(--line); font-weight: 600;
    }}
    tr.total th, tr.total td {{
      font-weight: 600;
      border-top: 1px solid var(--ink);
      border-bottom: 1px solid var(--ink);
    }}
    td.neg, td.amt.loss {{
      color: var(--bad);
      font-weight: 600;
    }}
    td.amt.profit {{
      color: var(--good);
      font-weight: 600;
    }}
    .oneoff-stmt td.amt.loss {{
      background: rgba(185, 28, 28, 0.06);
    }}
    .oneoff-stmt td.amt.profit {{
      background: rgba(74, 124, 89, 0.08);
    }}
    .trend-table th, .trend-table td {{
      font-size: 0.85rem;
      padding: 0.4rem 0.35rem;
    }}
    .trend-table thead th {{ font-size: 0.68rem; }}
    .spark-cell {{ width: 80px; text-align: center !important; }}
    .spark {{ display: inline-block; vertical-align: middle; }}
    .spark.empty {{ color: var(--muted); font-size: 0.8rem; }}
    .oneoff-stmt td.nature {{
      text-align: left;
      font-size: 0.82rem;
      color: var(--muted);
      max-width: 22rem;
    }}
    .oneoff-empty {{
      margin: 0.35rem 0 0.85rem;
      font-size: 0.92rem;
      color: var(--muted);
    }}
    .oneoff-head {{
      display: flex; flex-wrap: wrap; align-items: center;
      justify-content: space-between; gap: 0.5rem 1rem;
      margin-bottom: 0.35rem;
    }}
    .oneoff-head h3 {{ margin: 0; }}
    .oneoff-stmt h3.subhead {{
      margin: 1.1rem 0 0.55rem;
      font-size: 0.88rem;
      color: var(--accent);
    }}
    .extract-badge {{
      display: inline-block;
      font-size: 0.68rem;
      font-weight: 600;
      letter-spacing: 0.02em;
      padding: 0.28rem 0.55rem;
      border-radius: 6px;
      border: 1px solid var(--line);
      background: #eef2f6;
      color: var(--muted);
      max-width: 100%;
    }}
    .extract-badge.high {{
      border-color: #86efac; background: #f0fdf4; color: var(--good);
    }}
    .extract-badge.medium {{
      border-color: #fdba74; background: #fff7ed; color: var(--warn);
    }}
    .extract-badge.low {{
      border-color: #f1c0cc; background: #fff1f2; color: var(--bad);
    }}
    .coverage-note {{
      margin: 0 0 0.75rem;
      font-size: 0.82rem;
      color: var(--ink);
      background: #e8f1f8;
      border-radius: 8px;
      padding: 0.55rem 0.75rem;
    }}
    .analysis-block {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 1.25rem 1.35rem;
    }}
    .analysis-block .verdict-row {{
      display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.85rem;
    }}
    .analysis-block .lead {{
      font-family: "Libre Baskerville", Georgia, serif;
      font-size: 1.1rem; margin: 0 0 1rem;
    }}
    .analysis-block p {{ margin: 0 0 0.85rem; }}
    .analysis-block p:last-child {{ margin-bottom: 0; }}
    .checks {{ display: grid; gap: 0.85rem; margin-top: 1.1rem; }}
    @media (min-width: 720px) {{
      .checks {{ grid-template-columns: repeat(3, 1fr); }}
    }}
    .check {{
      background: #eef2f6;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 0.9rem 1rem;
    }}
    .check h3 {{ margin: 0 0 0.35rem; font-size: 0.9rem; color: var(--accent); }}
    .check p {{ margin: 0; font-size: 0.88rem; }}
    .source {{
      margin-top: 2rem; padding-top: 1rem; border-top: 1px solid var(--line);
      font-size: 0.8rem; color: var(--muted);
    }}
    .source a {{ color: var(--accent); }}
    .reaction-panel {{
      margin: 2.25rem 0 0;
      padding: 1.35rem 1.25rem 1.5rem;
      border-radius: 12px;
      border: 1px solid var(--line);
      background:
        linear-gradient(165deg, rgba(106, 158, 196, 0.12) 0%, transparent 55%),
        var(--card);
      text-align: center;
    }}
    .reaction-panel-title {{
      margin: 0 0 0.35rem;
      font-family: "Libre Baskerville", Georgia, serif;
      font-size: 1.15rem;
      color: var(--ink);
    }}
    .reaction-container {{
      margin-top: 1rem;
      display: flex; justify-content: center; align-items: center;
      gap: 0.75rem; flex-wrap: wrap;
    }}
    .reaction-btn {{
      display: inline-flex; align-items: center; justify-content: center;
      gap: 0.45rem; min-width: 7.5rem;
      padding: 0.7rem 1.15rem;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--muted);
      font: inherit; font-size: 0.95rem; font-weight: 600;
      cursor: pointer;
      transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.15s ease, color 0.15s ease;
    }}
    .reaction-btn:hover {{
      transform: translateY(-1px);
      box-shadow: 0 4px 14px rgba(44, 48, 54, 0.08);
      color: var(--ink);
    }}
    .reaction-btn.active-like {{
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }}
    .reaction-btn.active-dislike {{
      background: #c4785a;
      border-color: #c4785a;
      color: #fff;
    }}
    .reaction-btn .ico {{ font-size: 1.1rem; line-height: 1; }}
    @keyframes rise {{
      from {{ opacity: 0; transform: translateY(8px); }}
      to {{ opacity: 1; transform: none; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topnav">
      <a class="brand" href="../index.html">
        <img class="brand-logo-sm" src="../assets/companydb_logo.png" alt="CompanyDB" />
      </a>
      <a class="nav-link" href="../compare.html">Compare trends</a>
    </div>
    <h1>{analysis["company_en"]}</h1>
    <p class="sub">Ticker {analysis["ticker"]} · <span class="market-inline" title="{htmlmod.escape(market_label(market))}">{market_flag(market)} {htmlmod.escape(market_label(market))}</span> · Consolidated {accounting} · amounts in {currency_word}</p>
    <div class="meta-line">
      <span>{meta.get("docDescription") or "Annual securities report"}</span>
      <span>Filing date: {meta.get("date") or "—"}</span>
      <span class="badge {verdict_cls}">{analysis["verdict"]}</span>
    </div>
    {f'<p class="fresh-strip">{fresh_html}</p>' if fresh_html else ""}

    <section class="judgment" aria-label="Investor takeaway">
      <div class="judgment-top">
        <p class="judgment-kicker">Takeaway</p>
        <span class="action-badge {action_cls}">{htmlmod.escape(action)}</span>
      </div>
      <h2>{htmlmod.escape(judgment.get("what") or analysis["headline"])}</h2>
      <p class="why">{htmlmod.escape(judgment.get("why") or "")}</p>
      <p class="action-why">{htmlmod.escape(judgment.get("action_why") or "")}</p>
      <div class="snap-row">
        {snap_html}
      </div>
      <h3>Look at next</h3>
      <ol>
        {next_html}
      </ol>
    </section>

    <div class="period-bar">
      <label for="period-focus">Focus year</label>
      <select id="period-focus" aria-label="Select fiscal year to focus">
        {options_html}
      </select>
    </div>

    <section class="about" aria-label="About the company">
      <h2>About the company</h2>
      <p>{htmlmod.escape(about.get("summary") or "")}</p>
      {chips_html}
      {segments_html}
      {company_links_html}
    </section>

    <section>
      <h2>Financial statements</h2>
      {stmt_table("Income statement", stmts["income"])}
      {stmt_table("Balance sheet", stmts["balance"])}
      {stmt_table("Cash flow statement", stmts["cashflow"])}
    </section>

    <section>
      <h2>Five-year trends</h2>
      {trends_table or '<p class="section-sub">No multi-year summary metrics found in this filing.</p>'}
    </section>

    <section>
      <h2>How we read these numbers</h2>
      {one_offs_html}
      <div class="analysis-block">
        <div class="verdict-row">
          <span class="badge {verdict_cls}">{analysis["verdict"]}</span>
        </div>
        <p class="lead">{analysis["headline"]}</p>
        {paras_html}
        <div class="checks">
          {checks_html}
        </div>
      </div>
    </section>

    {reaction_panel_html(analysis["ticker"])}

    <div class="source">
      Source: {filing_system} <a href="{analysis["source_url"]}">{htmlmod.escape(str(meta.get("docID") or ""))}</a>
      ({htmlmod.escape(meta.get("filerName") or "")}), period end {htmlmod.escape(str(meta.get("periodEnd") or "—"))}.
    </div>
  </div>
  <script type="application/json" id="period-years">{years_json}</script>
  <script>
  (function () {{
    const years = JSON.parse(document.getElementById("period-years").textContent || "[]");
    const select = document.getElementById("period-focus");
    if (!select || years.length === 0) return;

    function applyFocus(focusId) {{
      const focus = years.find(y => y.id === focusId) || years[years.length - 1];
      const prior = years.find(y => y.key === "prior");
      const cur = years.find(y => y.key === "cur");
      const focusIsCur = focus.key === "cur";

      document.querySelectorAll(".stmt-table").forEach(table => {{
        const priorH = table.querySelector(".col-prior-h");
        const curH = table.querySelector(".col-cur-h");
        if (priorH && curH && prior && cur) {{
          if (focusIsCur) {{
            priorH.textContent = prior.label;
            curH.textContent = cur.label;
          }} else {{
            // Keep chronological order: older | newer, highlight the focused year.
            priorH.textContent = prior.label;
            curH.textContent = cur.label;
          }}
          priorH.classList.toggle("focus", !focusIsCur);
          curH.classList.toggle("focus", focusIsCur);
        }}
        table.querySelectorAll("tbody tr").forEach(tr => {{
          const p = tr.querySelector(".col-prior");
          const c = tr.querySelector(".col-cur");
          if (!p || !c) return;
          p.classList.toggle("focus-col", !focusIsCur);
          c.classList.toggle("focus-col", focusIsCur);
        }});
      }});
    }}

    select.addEventListener("change", () => applyFocus(select.value));
    applyFocus(select.value);
  }})();
  </script>
</body>
</html>
"""


def _write_facts_json(
    facts_path: Path,
    meta: dict,
    facts: dict,
    profile: dict,
    one_offs: dict | None = None,
) -> None:
    FACTS_DIR.mkdir(parents=True, exist_ok=True)
    payload: dict = {"meta": meta, "facts": facts, "profile": profile}
    if one_offs:
        payload["one_offs"] = one_offs
    facts_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def catalog_tickers() -> set[str]:
    """Tickers that already have a page or catalog entry."""
    out: set[str] = set()
    if CATALOG_PATH.exists():
        try:
            for c in json.loads(CATALOG_PATH.read_text(encoding="utf-8")):
                if c.get("ticker"):
                    out.add(str(c["ticker"]))
        except json.JSONDecodeError:
            pass
    if OUT_DIR.exists():
        for p in OUT_DIR.glob("*.html"):
            out.add(p.stem)
    return out


def upsert_catalog(analysis: dict) -> list[dict]:
    """Keep a company list for the top page and trend compare."""
    enrich_judgment(analysis)
    one_offs = analysis.get("one_offs") or {}
    adj = one_offs.get("adjusted_op") or {}
    meta = analysis.get("meta") or {}
    contacts = analysis.get("contacts") or {}
    trends = analysis.get("trends") or {}
    judgment = analysis.get("judgment") or {}
    valuation = analysis.get("valuation") or {}
    snapshot = analysis.get("snapshot") or {}
    # Slim trends payload for the compare page (years + series values only).
    trend_payload = {
        "years": [
            {"id": y.get("id"), "short": y.get("short")}
            for y in (trends.get("years") or [])
        ],
        "series": [
            {
                "id": s.get("id"),
                "label": s.get("label"),
                "values": s.get("values"),
            }
            for s in (trends.get("series") or [])
        ],
    }
    entry = {
        "ticker": analysis["ticker"],
        "company_en": analysis["company_en"],
        "market": analysis.get("market") or "JP",
        "currency": analysis.get("currency")
        or {"JP": "JPY", "KR": "KRW", "US": "USD"}.get(
            (analysis.get("market") or "JP").upper(), "JPY"
        ),
        "verdict": analysis.get("verdict"),
        "headline": analysis.get("headline"),
        "action": judgment.get("action"),
        "takeaway_what": judgment.get("what"),
        "period_end": (analysis.get("periods") or {}).get("current_end"),
        "filing_date": meta.get("date"),
        "doc_id": meta.get("docID"),
        "impairment_total": one_offs.get("impairment_total"),
        "has_notes": bool(one_offs.get("items") or one_offs.get("adjusted_op")),
        "adjusted_op": adj.get("adjusted_op"),
        "reported_op": adj.get("reported_op"),
        "op_margin": snapshot.get("op_margin"),
        "equity_ratio": snapshot.get("equity_ratio"),
        "price_label": valuation.get("price_label"),
        "trailing_pe": valuation.get("trailing_pe"),
        "ir_en_url": analysis.get("ir_en_url"),
        "contacts": {
            "phone": contacts.get("phone"),
            "email": contacts.get("email"),
            "as_of": contacts.get("as_of") or meta.get("date"),
            "source": contacts.get("source") or "EDINET annual securities report",
        },
        "trends": trend_payload,
        "href": f"companies/{analysis['ticker']}.html",
        "updated": analysis.get("as_of"),
    }
    with _CATALOG_LOCK:
        catalog: list[dict] = []
        if CATALOG_PATH.exists():
            try:
                catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
                if not isinstance(catalog, list):
                    catalog = []
            except json.JSONDecodeError:
                catalog = []
        catalog = [c for c in catalog if c.get("ticker") != entry["ticker"]]
        catalog.append(entry)
        catalog.sort(key=lambda c: c.get("ticker") or "")
        CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CATALOG_PATH.write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return list(catalog)


def render_index(catalog: list[dict]) -> str:
    def company_rows() -> str:
        if not catalog:
            return '<p class="empty">No company pages yet. Run the build script to add one.</p>'
        parts = []
        for i, c in enumerate(catalog):
            v = (c.get("verdict") or "Mixed").lower()
            market = (c.get("market") or "JP").upper()
            market_cls = {"JP": "jp", "KR": "kr", "US": "us"}.get(market, "xx")
            stripe = "even" if i % 2 == 0 else "odd"
            href = htmlmod.escape(c.get("href") or "#")
            name = htmlmod.escape(c.get("company_en") or "Company")
            ticker = htmlmod.escape(c.get("ticker") or "")
            headline = htmlmod.escape(
                c.get("takeaway_what") or c.get("headline") or ""
            )
            action = htmlmod.escape(c.get("action") or "")
            period = htmlmod.escape(c.get("period_end") or "")
            hay = htmlmod.escape(
                f"{c.get('ticker') or ''} {c.get('company_en') or ''} {market} {c.get('action') or ''}".lower()
            )
            flag = market_flag(market)
            mlabel = market_label(market)
            action_bit = (
                f'<span class="co-action">{action}</span>' if action else ""
            )
            parts.append(
                f'<a class="co-row market-{market_cls} stripe-{stripe}" href="{href}" data-q="{hay}">'
                f'<span class="co-ticker">{ticker}</span>'
                f'<span class="co-main">'
                f'<span class="co-name-row">'
                f'<span class="co-name">{name}</span>'
                f'<span class="market-flag" title="{htmlmod.escape(mlabel)}" '
                f'aria-label="{htmlmod.escape(mlabel)}">{flag}</span>'
                f"</span>"
                f'<span class="co-line">{headline}</span>'
                f"{action_bit}"
                f"</span>"
                f'<span class="co-meta">'
                f'<span class="badge {htmlmod.escape(v)}">{htmlmod.escape(c.get("verdict") or "Mixed")}</span>'
                f'<span class="co-period">{period}</span>'
                f"</span>"
                f"</a>"
            )
        return "\n".join(parts)

    count = len(catalog)
    jp_n = sum(1 for c in catalog if (c.get("market") or "JP").upper() == "JP")
    kr_n = sum(1 for c in catalog if (c.get("market") or "").upper() == "KR")
    us_n = sum(1 for c in catalog if (c.get("market") or "").upper() == "US")
    coverage_bits = []
    if jp_n:
        coverage_bits.append(f"🇯🇵 {jp_n}")
    if kr_n:
        coverage_bits.append(f"🇰🇷 {kr_n}")
    if us_n:
        coverage_bits.append(f"🇺🇸 {us_n}")
    coverage_line = " · ".join(coverage_bits) if coverage_bits else ""

    dig_n = sum(1 for c in catalog if c.get("action") == "Dig deeper")
    track_n = sum(1 for c in catalog if c.get("action") == "Worth tracking")
    park_n = sum(1 for c in catalog if c.get("action") == "Park for now")

    def _page_has_notes(c: dict) -> bool:
        if c.get("has_notes") or c.get("impairment_total"):
            return True
        path = OUT_DIR / f"{c.get('ticker')}.html"
        if not path.exists():
            return False
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return False
        return 'class="amt loss"' in text or 'class="amt profit"' in text

    notes_n = sum(1 for c in catalog if _page_has_notes(c))
    notes_empty_n = max(0, count - notes_n)

    def _fresh_key(c: dict) -> str:
        return str(c.get("updated") or c.get("filing_date") or c.get("period_end") or "")

    newest: list[dict] = []
    for market in ("JP", "KR", "US"):
        peers = [c for c in catalog if (c.get("market") or "JP").upper() == market]
        if not peers:
            continue
        newest.append(max(peers, key=_fresh_key))
    newest_html_parts = []
    for c in newest:
        href = htmlmod.escape(c.get("href") or "#")
        name = htmlmod.escape(c.get("company_en") or "Company")
        ticker = htmlmod.escape(c.get("ticker") or "")
        when = htmlmod.escape(_fresh_key(c) or "—")
        flag = market_flag(c.get("market"))
        newest_html_parts.append(
            f'<a class="fresh-row" href="{href}">'
            f'<span class="fresh-name">{flag} {name}</span>'
            f'<span class="fresh-meta">{ticker} · {when}</span>'
            f"</a>"
        )
    newest_html = (
        "".join(newest_html_parts)
        if newest_html_parts
        else '<p class="fresh-empty">No recent updates yet.</p>'
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
{GA_HEAD}  <title>CompanyDB — Filings, read in English</title>
  <meta name="description" content="Plain-English financial statements and note-driven takeaways from Japan, Korea, and the US — EDINET, DART, and SEC." />
  <link rel="icon" href="assets/favicon.ico" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Libre+Baskerville:wght@400;700&display=swap" rel="stylesheet" />
  <style>
{css_vars()}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", system-ui, sans-serif;
      color: var(--ink);
      background: var(--paper);
      line-height: 1.55;
    }}
    a {{ color: inherit; }}

    .hero {{
      min-height: 100vh;
      min-height: 100dvh;
      display: grid;
      grid-template-rows: 1fr auto;
      background:
        radial-gradient(900px 520px at 12% 0%, #d4e5f2 0%, transparent 55%),
        radial-gradient(800px 480px at 95% 15%, #e8dcc4 0%, transparent 50%),
        linear-gradient(180deg, #e8eef4 0%, var(--paper) 70%);
    }}
    .hero-copy {{
      max-width: 880px;
      margin: 0 auto;
      padding: clamp(2.5rem, 8vh, 5rem) 1.25rem 1.5rem;
      display: flex;
      flex-direction: column;
      justify-content: flex-end;
    }}
    .brand-logo {{
      display: block;
      width: min(320px, 72vw);
      height: auto;
      margin: 0 0 1.15rem;
      animation: rise 0.7s ease both;
    }}
    .hero-copy h1 {{
      font-family: "Libre Baskerville", Georgia, serif;
      font-size: clamp(1.35rem, 3.2vw, 1.85rem);
      font-weight: 400;
      line-height: 1.3;
      margin: 0 0 0.75rem;
      max-width: 22ch;
      animation: rise 0.75s ease 0.08s both;
    }}
    .hero-copy .lede {{
      margin: 0 0 0.85rem;
      max-width: 36rem;
      color: var(--muted);
      font-size: 1.05rem;
      animation: rise 0.75s ease 0.14s both;
    }}
    .coverage-count {{
      margin: 0 0 1.35rem;
      font-size: 0.95rem;
      color: var(--ink);
      animation: rise 0.75s ease 0.16s both;
    }}
    .coverage-count strong {{
      font-size: 1.15rem;
      font-variant-numeric: tabular-nums;
      color: var(--accent-deep);
    }}
    .coverage-split {{
      margin-left: 0.55rem;
      color: var(--muted);
      font-size: 0.88rem;
    }}
    .co-total {{
      display: inline-block;
      margin-left: 0.35rem;
      padding: 0.12rem 0.55rem;
      border-radius: 999px;
      font-size: 0.85rem;
      font-weight: 600;
      font-variant-numeric: tabular-nums;
      vertical-align: middle;
      color: var(--accent-deep);
      background: var(--accent-soft);
      border: 1px solid #b7cfe0;
    }}
    .cta-row {{
      display: flex; flex-wrap: wrap; gap: 0.65rem 0.85rem;
      animation: rise 0.75s ease 0.2s both;
    }}
    .cta {{
      display: inline-flex;
      align-items: center;
      gap: 0.55rem;
      width: fit-content;
      padding: 0.85rem 1.2rem;
      background: var(--accent-deep);
      color: #fff;
      text-decoration: none;
      font-weight: 600;
      font-size: 0.95rem;
      border-radius: 10px;
      transition: background 0.2s ease, transform 0.2s ease;
    }}
    .cta:hover {{ background: #2c3036; transform: translateY(-1px); }}
    .cta.secondary {{
      background: transparent;
      color: var(--accent-deep);
      border: 1px solid var(--accent);
    }}
    .cta.secondary:hover {{ background: rgba(106, 158, 196, 0.12); }}
    .cta .arrow {{
      display: inline-block;
      transition: transform 0.2s ease;
    }}
    .cta:hover .arrow {{ transform: translateX(3px); }}

    .product-plane {{
      width: 100%;
      border-top: 1px solid rgba(44, 48, 54, 0.12);
      background:
        linear-gradient(135deg, #5a7a96 0%, #3d4f63 45%, #2c3036 100%);
      color: #eef3f7;
      animation: plane-in 0.9s ease 0.15s both;
    }}
    .product-plane-inner {{
      max-width: 880px;
      margin: 0 auto;
      padding: 1.5rem 1.25rem 1.75rem;
      display: grid;
      gap: 1.35rem 1.5rem;
    }}
    @media (min-width: 720px) {{
      .product-plane-inner {{
        grid-template-columns: 1.1fr 0.9fr 1.2fr;
        align-items: start;
      }}
    }}
    .plane-block {{
      border-top: 1px solid rgba(232, 245, 241, 0.22);
      padding-top: 0.65rem;
      animation: metric-fade 0.8s ease both;
    }}
    .plane-block:nth-child(2) {{ animation-delay: 0.08s; }}
    .plane-block:nth-child(3) {{ animation-delay: 0.16s; }}
    .plane-kicker {{
      font-size: 0.72rem;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      opacity: 0.7;
      margin: 0 0 0.55rem;
    }}
    .plane-pulse {{
      display: grid;
      gap: 0.45rem;
    }}
    .pulse-row {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 0.75rem;
      font-variant-numeric: tabular-nums;
    }}
    .pulse-row span {{
      font-size: 0.82rem;
      opacity: 0.78;
    }}
    .pulse-row strong {{
      font-size: 1.15rem;
      font-weight: 600;
    }}
    .plane-notes-line {{
      margin: 0;
      font-size: 1.05rem;
      font-weight: 600;
      font-variant-numeric: tabular-nums;
      line-height: 1.35;
    }}
    .plane-notes-line em {{
      font-style: normal;
      opacity: 0.72;
      font-weight: 500;
      font-size: 0.88rem;
    }}
    .fresh-list {{
      display: grid;
      gap: 0.4rem;
    }}
    .fresh-row {{
      display: flex;
      flex-direction: column;
      gap: 0.1rem;
      color: inherit;
      text-decoration: none;
      padding: 0.25rem 0;
      border-radius: 4px;
      transition: background 0.15s ease;
    }}
    .fresh-row:hover {{
      background: rgba(255, 255, 255, 0.06);
    }}
    .fresh-name {{
      font-size: 0.92rem;
      font-weight: 600;
    }}
    .fresh-meta {{
      font-size: 0.75rem;
      opacity: 0.65;
      font-variant-numeric: tabular-nums;
    }}
    .fresh-empty {{
      margin: 0;
      font-size: 0.88rem;
      opacity: 0.7;
    }}

    .wrap {{
      max-width: 880px;
      margin: 0 auto;
      padding: 3rem 1.25rem 4rem;
    }}
    section {{ margin-top: 2.75rem; }}
    section:first-child {{ margin-top: 0; }}
    section > h2 {{
      font-family: "Libre Baskerville", Georgia, serif;
      font-size: 1.45rem;
      margin: 0 0 0.35rem;
    }}
    .section-sub {{
      color: var(--muted);
      margin: 0 0 1.25rem;
      max-width: 40rem;
    }}

    .index-search {{
      width: 100%;
      font: inherit;
      font-size: 0.98rem;
      padding: 0.7rem 0.85rem;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: var(--card);
      color: var(--ink);
      margin: 0 0 0.85rem;
    }}
    .index-search:focus {{
      outline: 2px solid rgba(106, 158, 196, 0.4);
      border-color: var(--accent);
    }}
    .co-count {{
      font-size: 0.8rem;
      color: var(--muted);
      margin: 0 0 0.65rem;
    }}
    .co-list {{
      display: flex;
      flex-direction: column;
      gap: 0.55rem;
      max-height: min(70vh, 720px);
      overflow: auto;
      padding: 0.75rem;
      border-radius: 14px;
      border: 1px solid #c5d8d1;
      background:
        linear-gradient(165deg, rgba(106, 158, 196, 0.18) 0%, transparent 45%),
        linear-gradient(345deg, rgba(196, 164, 132, 0.12) 0%, transparent 42%),
        linear-gradient(180deg, #e8eef4 0%, #f2f4f7 100%);
    }}
    .co-row {{
      display: grid;
      grid-template-columns: 3.6rem minmax(0, 1fr) auto;
      gap: 0.55rem 0.75rem;
      align-items: center;
      height: 5.75rem;
      min-height: 5.75rem;
      max-height: 5.75rem;
      padding: 0 0.85rem 0 0.95rem;
      border-radius: 10px;
      border: 1px solid transparent;
      border-left-width: 4px;
      text-decoration: none;
      overflow: hidden;
      transition: transform 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease;
    }}
    .co-row.is-hidden {{ display: none; }}
    /* Japan — teal / sage gradients, alternating so rows don't blend */
    .co-row.market-jp.stripe-even {{
      border-left-color: #6a9ec4;
      background: linear-gradient(105deg, #d4e5f2 0%, #e8f1f8 38%, #ffffff 100%);
    }}
    .co-row.market-jp.stripe-odd {{
      border-left-color: #7aabd0;
      background: linear-gradient(105deg, #c5dcef 0%, #dceaf4 40%, #eef2f6 100%);
    }}
    /* Korea — prepared blue/indigo wash (unused until KR names land) */
    .co-row.market-kr.stripe-even {{
      border-left-color: #c4a484;
      background: linear-gradient(105deg, #f3e8dc 0%, #f7efe6 40%, #ffffff 100%);
    }}
    .co-row.market-kr.stripe-odd {{
      border-left-color: #d2b48c;
      background: linear-gradient(105deg, #edd9c4 0%, #f3e6d8 40%, #eef2f6 100%);
    }}
    /* United States — soft slate (not dark blue) */
    .co-row.market-us.stripe-even {{
      border-left-color: #7a8fa3;
      background: linear-gradient(105deg, #e2e8f0 0%, #eef2f6 40%, #ffffff 100%);
    }}
    .co-row.market-us.stripe-odd {{
      border-left-color: #94a3b8;
      background: linear-gradient(105deg, #d7e0ea 0%, #e8eef4 40%, #f5f6f8 100%);
    }}
    .co-row.market-xx {{
      border-left-color: #78716c;
      background: linear-gradient(105deg, #e7e5e4 0%, #ffffff 100%);
    }}
    .co-row:hover {{
      transform: translateY(-1px);
      box-shadow: 0 6px 18px rgba(20, 32, 28, 0.1);
      filter: saturate(1.05);
    }}
    .co-ticker {{
      font-weight: 600;
      font-variant-numeric: tabular-nums;
      color: var(--accent-deep);
      align-self: center;
    }}
    .co-main {{
      display: flex;
      flex-direction: column;
      justify-content: center;
      gap: 0.15rem;
      min-width: 0;
      overflow: hidden;
    }}
    .co-name-row {{
      display: flex; flex-wrap: nowrap; align-items: center; gap: 0.4rem 0.5rem;
      min-width: 0;
    }}
    .co-name {{
      font-family: "Libre Baskerville", Georgia, serif;
      font-size: 1rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      min-width: 0;
    }}
    .market-flag {{
      display: inline-flex;
      flex-shrink: 0;
      align-items: center;
      justify-content: center;
      font-size: 1.15rem;
      line-height: 1;
      filter: drop-shadow(0 0 0.5px rgba(44, 48, 54, 0.25));
    }}
    .co-line {{
      font-size: 0.8rem;
      line-height: 1.3;
      height: calc(0.8rem * 1.3);
      color: #3d4a44;
      display: -webkit-box;
      -webkit-line-clamp: 1;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}
    .co-action {{
      display: inline-block;
      margin-top: 0.2rem;
      font-size: 0.7rem;
      font-weight: 600;
      letter-spacing: 0.03em;
      color: var(--accent-deep);
    }}
    .co-meta {{
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      justify-content: center;
      gap: 0.3rem;
      text-align: right;
      flex-shrink: 0;
      width: 6.75rem;
    }}
    .co-period {{
      font-size: 0.72rem;
      color: var(--muted);
      white-space: nowrap;
    }}
    @media (max-width: 520px) {{
      .co-row {{
        grid-template-columns: 3.2rem minmax(0, 1fr);
        height: 5.5rem;
        min-height: 5.5rem;
        max-height: 5.5rem;
      }}
      .co-meta {{ display: none; }}
    }}
    .badge {{
      display: inline-block; padding: 0.28rem 0.6rem; border-radius: 999px;
      font-size: 0.68rem; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase;
      border: 1px solid var(--line); background: rgba(255, 253, 248, 0.9);
    }}
    .badge.challenged {{ color: var(--warn); border-color: #fdba74; background: #fff7ed; }}
    .badge.constructive {{ color: var(--good); border-color: #86efac; background: #f0fdf4; }}
    .badge.mixed {{ color: var(--muted); }}
    .empty {{ color: var(--muted); }}

    .steps {{
      display: grid;
      gap: 1.25rem;
      counter-reset: step;
    }}
    @media (min-width: 720px) {{
      .steps {{ grid-template-columns: repeat(2, 1fr); gap: 1.25rem 1.5rem; }}
    }}
    @media (min-width: 960px) {{
      .steps {{ grid-template-columns: repeat(4, 1fr); }}
    }}
    .step {{
      border-top: 2px solid var(--accent);
      padding-top: 0.85rem;
    }}
    .step h3 {{
      margin: 0 0 0.4rem;
      font-size: 1rem;
    }}
    .step h3::before {{
      counter-increment: step;
      content: counter(step) ". ";
      color: var(--accent);
      font-weight: 600;
    }}
    .step p {{
      margin: 0;
      font-size: 0.92rem;
      color: var(--muted);
    }}

    .footer {{
      margin-top: 3rem;
      padding-top: 1.25rem;
      border-top: 1px solid var(--line);
      font-size: 0.8rem;
      color: var(--muted);
    }}
    .footer a {{ color: var(--accent); }}

    @keyframes rise {{
      from {{ opacity: 0; transform: translateY(12px); }}
      to {{ opacity: 1; transform: none; }}
    }}
    @keyframes plane-in {{
      from {{ opacity: 0; transform: translateY(16px); }}
      to {{ opacity: 1; transform: none; }}
    }}
    @keyframes metric-fade {{
      from {{ opacity: 0; transform: translateY(6px); }}
      to {{ opacity: 1; transform: none; }}
    }}
  </style>
</head>
<body>
  <header class="hero">
    <div class="hero-copy">
      <img class="brand-logo" src="assets/companydb_logo.png" width="320" height="120"
        alt="CompanyDB" />
      <h1>Public filings, read in English.</h1>
      <p class="lede">
        Statements and note-driven takeaways for personal investors — Japan, Korea, and the US.
      </p>
      <p class="coverage-count" aria-label="Company coverage">
        <strong>{count}</strong> compan{"y" if count == 1 else "ies"}
        {f'<span class="coverage-split">{coverage_line}</span>' if coverage_line else ""}
      </p>
      <div class="cta-row">
        <a class="cta" href="#companies">Browse companies <span class="arrow" aria-hidden="true">→</span></a>
        <a class="cta secondary" href="compare.html">Compare trends <span class="arrow" aria-hidden="true">→</span></a>
      </div>
    </div>
    <div class="product-plane" aria-label="Coverage pulse">
      <div class="product-plane-inner">
        <div class="plane-block">
          <p class="plane-kicker">Action pulse</p>
          <div class="plane-pulse">
            <div class="pulse-row"><span>Dig deeper</span><strong>{dig_n}</strong></div>
            <div class="pulse-row"><span>Worth tracking</span><strong>{track_n}</strong></div>
            <div class="pulse-row"><span>Park for now</span><strong>{park_n}</strong></div>
          </div>
        </div>
        <div class="plane-block">
          <p class="plane-kicker">Notes activity</p>
          <p class="plane-notes-line">
            {notes_n} with note findings
            <em>· {notes_empty_n} clear</em>
          </p>
        </div>
        <div class="plane-block">
          <p class="plane-kicker">Newest filings</p>
          <div class="fresh-list">
            {newest_html}
          </div>
        </div>
      </div>
    </div>
  </header>

  <main class="wrap">
    <section id="companies" aria-label="Companies">
      <h2>Companies <span class="co-total">{count}</span></h2>
      <p class="section-sub">
        {count} compan{"y" if count == 1 else "ies"}
        {f" ({coverage_line})" if coverage_line else ""}.
        Search by name or ticker, or
        <a href="compare.html" style="color:var(--accent)">compare trends</a>.
      </p>
      <input class="index-search" id="index-search" type="search" autocomplete="off"
        placeholder="Search companies (name or ticker)" aria-label="Search companies" />
      <p class="co-count" id="co-count"></p>
      <div class="co-list" id="co-list">
        {company_rows()}
      </div>
    </section>

    <section aria-label="How it works">
      <h2>How it works</h2>
      <div class="steps">
        <div class="step">
          <h3>Pull the filing</h3>
          <p>Annual reports from EDINET, DART, and SEC.</p>
        </div>
        <div class="step">
          <h3>Lay out the numbers</h3>
          <p>Two-year statements plus longer trends.</p>
        </div>
        <div class="step">
          <h3>Read the notes</h3>
          <p>Surface impairments and one-offs, then a clear takeaway.</p>
        </div>
      </div>
    </section>

    <footer class="footer">
      <p>
        Not investment advice. Figures from public filings —
        <a href="https://disclosure2.edinet-fsa.go.jp/">EDINET</a>, DART, SEC.
      </p>
    </footer>
  </main>
  <script>
  (function () {{
    const input = document.getElementById("index-search");
    const list = document.getElementById("co-list");
    const countEl = document.getElementById("co-count");
    if (!input || !list) return;
    const rows = Array.from(list.querySelectorAll(".co-row"));
    function refresh() {{
      const q = (input.value || "").trim().toLowerCase();
      let n = 0;
      for (const row of rows) {{
        const hay = row.getAttribute("data-q") || "";
        const show = !q || hay.includes(q);
        row.classList.toggle("is-hidden", !show);
        if (show) n++;
      }}
      if (countEl) {{
        countEl.textContent = q
          ? n + " match" + (n === 1 ? "" : "es") + " of " + rows.length
          : rows.length + " companies";
      }}
    }}
    input.addEventListener("input", refresh);
    refresh();
  }})();
  </script>
</body>
</html>
"""


def render_compare(catalog: list[dict]) -> str:
    """Search-first multi-company trends page (scales to 100+ names)."""
    payload = []
    for c in catalog:
        payload.append(
            {
                "ticker": c.get("ticker"),
                "company_en": c.get("company_en"),
                "market": c.get("market") or "JP",
                "currency": c.get("currency")
                or {"JP": "JPY", "KR": "KRW", "US": "USD"}.get(
                    (c.get("market") or "JP").upper(), "JPY"
                ),
                "verdict": c.get("verdict"),
                "action": c.get("action"),
                "href": c.get("href"),
                "trends": c.get("trends") or {"years": [], "series": []},
            }
        )
    data_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    universe = len(catalog)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
{GA_HEAD}  <title>Compare trends — CompanyDB</title>
  <meta name="description" content="Search companies across Japan, Korea, and the US and overlay five-year financial trends." />
  <link rel="icon" href="assets/favicon.ico" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Libre+Baskerville:wght@400;700&display=swap" rel="stylesheet" />
  <style>
{css_vars()}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", system-ui, sans-serif;
      color: var(--ink);
      background:
        radial-gradient(1000px 500px at 8% -10%, #dce8f2 0%, transparent 55%),
        radial-gradient(800px 420px at 100% 0%, #ebe4d8 0%, transparent 50%),
        var(--paper);
      line-height: 1.55;
    }}
    .wrap {{ max-width: 960px; margin: 0 auto; padding: 2rem 1.25rem 4rem; }}
    .topnav {{
      display: flex; flex-wrap: wrap; align-items: center;
      justify-content: space-between; gap: 0.5rem 1rem; margin-bottom: 0.85rem;
    }}
    .brand {{
      display: inline-flex; align-items: center; text-decoration: none;
    }}
    .brand-logo-sm {{
      display: block; height: 40px; width: auto;
    }}
    .nav-link {{ font-size: 0.85rem; color: var(--accent-deep); text-decoration: none; font-weight: 500; }}
    h1 {{
      font-family: "Libre Baskerville", Georgia, serif;
      font-size: clamp(1.6rem, 3.5vw, 2.1rem);
      margin: 0 0 0.4rem; line-height: 1.2;
    }}
    .lede {{ color: var(--muted); margin: 0 0 1.5rem; max-width: 42rem; }}
    .panel {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 1.1rem 1.2rem 1.25rem;
      margin-bottom: 1rem;
      animation: rise 0.55s ease both;
    }}
    .panel h2 {{
      font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em;
      color: var(--accent-deep); margin: 0 0 0.75rem;
    }}
    .search-wrap {{ position: relative; }}
    #co-search {{
      width: 100%;
      font: inherit;
      font-size: 1rem;
      padding: 0.75rem 0.9rem;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: #ffffff;
      color: var(--ink);
    }}
    #co-search:focus {{
      outline: 2px solid rgba(106, 158, 196, 0.4);
      border-color: var(--accent);
    }}
    .results {{
      position: absolute;
      left: 0; right: 0; top: calc(100% + 4px);
      z-index: 20;
      max-height: 280px;
      overflow: auto;
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 10px;
      box-shadow: 0 10px 28px rgba(20, 32, 28, 0.1);
      display: none;
    }}
    .results.open {{ display: block; }}
    .result-row {{
      display: grid;
      grid-template-columns: 4.2rem 1fr auto;
      gap: 0.55rem;
      align-items: center;
      width: 100%;
      padding: 0.65rem 0.85rem;
      border: 0;
      border-bottom: 1px solid #ebe6da;
      background: transparent;
      text-align: left;
      font: inherit;
      cursor: pointer;
      color: var(--ink);
    }}
    .result-row:last-child {{ border-bottom: 0; }}
    .result-row:hover, .result-row.active {{ background: #e8f1f8; }}
    .result-row:disabled {{ opacity: 0.45; cursor: not-allowed; }}
    .result-ticker {{
      font-weight: 600; color: var(--accent);
      font-variant-numeric: tabular-nums;
    }}
    .result-name {{ font-size: 0.92rem; }}
    .result-meta {{ font-size: 0.72rem; color: var(--muted); text-transform: uppercase; }}
    .chips {{
      display: flex; flex-wrap: wrap; gap: 0.45rem;
      min-height: 2rem;
      margin-top: 0.85rem;
    }}
    .chip {{
      display: inline-flex; align-items: center; gap: 0.4rem;
      padding: 0.35rem 0.35rem 0.35rem 0.7rem;
      border-radius: 999px;
      border: 1px solid var(--accent);
      background: #e8f1f8;
      font-size: 0.85rem;
      font-weight: 500;
    }}
    .chip button {{
      border: 0; background: transparent; cursor: pointer;
      color: var(--accent-deep); font-size: 1rem; line-height: 1;
      padding: 0.15rem 0.45rem; border-radius: 999px;
    }}
    .chip button:hover {{ background: rgba(106, 158, 196, 0.14); }}
    .chips-empty {{ color: var(--muted); font-size: 0.88rem; }}
    .hint {{ font-size: 0.8rem; color: var(--muted); margin: 0.65rem 0 0; }}
    .controls {{
      display: flex; flex-wrap: wrap; gap: 0.85rem 1.25rem; align-items: end;
    }}
    .controls label {{
      display: flex; flex-direction: column; gap: 0.3rem;
      font-size: 0.72rem; font-weight: 600; letter-spacing: 0.04em;
      text-transform: uppercase; color: var(--accent);
    }}
    .controls select {{
      font: inherit; font-size: 0.95rem; text-transform: none; letter-spacing: 0;
      font-weight: 400; color: var(--ink);
      border: 1px solid var(--line); border-radius: 8px;
      padding: 0.5rem 0.7rem; background: #ffffff; min-width: 180px;
    }}
    .chart-wrap {{ position: relative; width: 100%; min-height: 320px; }}
    #chart {{ width: 100%; height: auto; display: block; }}
    .legend {{
      display: flex; flex-wrap: wrap; gap: 0.65rem 1.1rem; margin-top: 0.85rem;
    }}
    .legend-item {{
      display: inline-flex; align-items: center; gap: 0.4rem; font-size: 0.85rem;
    }}
    .legend-item a {{ color: inherit; }}
    .swatch {{ width: 12px; height: 12px; border-radius: 3px; flex-shrink: 0; }}
    .empty-msg {{
      color: var(--muted); font-size: 0.95rem; padding: 2rem 0; text-align: center;
    }}
    .footer {{
      margin-top: 2rem; padding-top: 1rem; border-top: 1px solid var(--line);
      font-size: 0.8rem; color: var(--muted);
    }}
    .footer a {{ color: var(--accent); }}
    @keyframes rise {{
      from {{ opacity: 0; transform: translateY(8px); }}
      to {{ opacity: 1; transform: none; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topnav">
      <a class="brand" href="index.html">
        <img class="brand-logo-sm" src="assets/companydb_logo.png" alt="CompanyDB" height="40" />
      </a>
      <a class="nav-link" href="index.html">All companies</a>
    </div>
    <h1>Compare five-year trends</h1>
    <p class="lede">
      Search {universe} companies, add up to four, overlay one metric.
    </p>

    <div class="panel">
      <h2>Add companies</h2>
      <div class="search-wrap">
        <input id="co-search" type="search" autocomplete="off"
          placeholder="Search by name or ticker (e.g. Sony, 6758)"
          aria-label="Search companies" aria-controls="co-results" />
        <div class="results" id="co-results" role="listbox" aria-label="Search results"></div>
      </div>
      <div class="chips" id="chips" aria-live="polite"></div>
      <p class="hint">Max 4 companies.</p>
    </div>

    <div class="panel">
      <h2>Chart</h2>
      <div class="controls">
        <label>Metric
          <select id="metric"></select>
        </label>
        <label>Scale
          <select id="scale">
            <option value="indexed" selected>Indexed (first year = 100)</option>
            <option value="absolute">Absolute</option>
          </select>
        </label>
      </div>
      <div class="chart-wrap">
        <svg id="chart" viewBox="0 0 880 340" role="img" aria-label="Trend comparison chart"></svg>
        <p class="empty-msg" id="empty">Search and add a company to start.</p>
      </div>
      <div class="legend" id="legend"></div>
    </div>

    <div class="footer">
      From public filings. Not investment advice.
    </div>
  </div>
  <script type="application/json" id="compare-data">{data_json}</script>
  <script>
  (function () {{
    const companies = JSON.parse(document.getElementById("compare-data").textContent || "[]");
    const byTicker = Object.fromEntries(companies.map(c => [c.ticker, c]));
    const COLORS = ["#6a9ec4", "#c4785a", "#8faf9a", "#c4a484"];
    const MAX = 4;
    const metricSel = document.getElementById("metric");
    const scaleSel = document.getElementById("scale");
    const svg = document.getElementById("chart");
    const legend = document.getElementById("legend");
    const empty = document.getElementById("empty");
    const search = document.getElementById("co-search");
    const results = document.getElementById("co-results");
    const chipsEl = document.getElementById("chips");

    let selected = companies.slice(0, Math.min(2, companies.length)).map(c => c.ticker);
    let activeIdx = 0;

    const metricIds = [];
    const metricLabels = {{}};
    for (const c of companies) {{
      for (const s of (c.trends && c.trends.series) || []) {{
        if (!metricLabels[s.id]) {{
          metricLabels[s.id] = s.label;
          metricIds.push(s.id);
        }}
      }}
    }}
    const preferred = ["revenue", "operating_profit", "profit_owners", "total_assets", "cash", "equity_owners"];
    metricIds.sort((a, b) => {{
      const ia = preferred.indexOf(a); const ib = preferred.indexOf(b);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    }});
    for (const id of metricIds) {{
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = metricLabels[id] || id;
      metricSel.appendChild(opt);
    }}
    if (metricIds.includes("revenue")) metricSel.value = "revenue";

    function norm(s) {{
      return (s || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
    }}

    function scoreMatch(c, q) {{
      if (!q) return 0;
      const ticker = (c.ticker || "").toLowerCase();
      const name = norm(c.company_en);
      const nq = norm(q);
      if (ticker === q.trim().toLowerCase()) return 100;
      if (ticker.startsWith(q.trim().toLowerCase())) return 90;
      if (name.startsWith(nq)) return 80;
      if (name.includes(nq)) return 60;
      if (ticker.includes(q.trim().toLowerCase())) return 50;
      return 0;
    }}

    function searchHits(q) {{
      const scored = companies
        .map(c => ({{ c, s: scoreMatch(c, q) }}))
        .filter(x => x.s > 0)
        .sort((a, b) => b.s - a.s || (a.c.ticker || "").localeCompare(b.c.ticker || ""));
      return scored.slice(0, 12).map(x => x.c);
    }}

    function renderChips() {{
      chipsEl.innerHTML = "";
      if (!selected.length) {{
        const span = document.createElement("span");
        span.className = "chips-empty";
        span.textContent = "No companies selected yet.";
        chipsEl.appendChild(span);
        return;
      }}
      selected.forEach((t, i) => {{
        const c = byTicker[t];
        if (!c) return;
        const chip = document.createElement("span");
        chip.className = "chip";
        chip.style.borderColor = COLORS[i % COLORS.length];
        chip.innerHTML =
          `<span>${{c.company_en}} <span style="color:var(--muted);font-weight:400">${{c.ticker}}</span></span>`;
        const btn = document.createElement("button");
        btn.type = "button";
        btn.setAttribute("aria-label", "Remove " + c.ticker);
        btn.textContent = "×";
        btn.addEventListener("click", () => {{
          selected = selected.filter(x => x !== t);
          renderChips();
          draw();
        }});
        chip.appendChild(btn);
        chipsEl.appendChild(chip);
      }});
    }}

    function addTicker(t) {{
      if (!t || !byTicker[t]) return;
      if (selected.includes(t)) return;
      if (selected.length >= MAX) return;
      selected.push(t);
      search.value = "";
      closeResults();
      renderChips();
      draw();
    }}

    function renderResults(hits) {{
      results.innerHTML = "";
      if (!hits.length) {{
        results.classList.remove("open");
        return;
      }}
      hits.forEach((c, i) => {{
        const already = selected.includes(c.ticker);
        const full = !already && selected.length >= MAX;
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "result-row" + (i === activeIdx ? " active" : "");
        btn.setAttribute("role", "option");
        btn.disabled = already || full;
        btn.innerHTML =
          `<span class="result-ticker">${{c.ticker}}</span>` +
          `<span class="result-name">${{c.company_en}}</span>` +
          `<span class="result-meta">${{already ? "Added" : (full ? "Max 4" : (({{"KR":"🇰🇷","US":"🇺🇸","JP":"🇯🇵"}}[c.market || "JP"] || "🏳️") + (c.action ? " · " + c.action : (c.verdict ? " · " + c.verdict : ""))))}}</span>`;
        btn.addEventListener("mousedown", (e) => {{
          e.preventDefault();
          addTicker(c.ticker);
        }});
        results.appendChild(btn);
      }});
      results.classList.add("open");
    }}

    function closeResults() {{
      results.classList.remove("open");
      results.innerHTML = "";
      activeIdx = 0;
    }}

    search.addEventListener("input", () => {{
      activeIdx = 0;
      const q = search.value.trim();
      if (q.length < 1) {{ closeResults(); return; }}
      renderResults(searchHits(q));
    }});
    search.addEventListener("keydown", (e) => {{
      const rows = Array.from(results.querySelectorAll(".result-row"));
      if (e.key === "ArrowDown" && rows.length) {{
        e.preventDefault();
        activeIdx = Math.min(rows.length - 1, activeIdx + 1);
        rows.forEach((r, i) => r.classList.toggle("active", i === activeIdx));
      }} else if (e.key === "ArrowUp" && rows.length) {{
        e.preventDefault();
        activeIdx = Math.max(0, activeIdx - 1);
        rows.forEach((r, i) => r.classList.toggle("active", i === activeIdx));
      }} else if (e.key === "Enter") {{
        e.preventDefault();
        const rows2 = Array.from(results.querySelectorAll(".result-row:not(:disabled)"));
        const pick = rows[activeIdx] && !rows[activeIdx].disabled
          ? rows[activeIdx]
          : rows2[0];
        if (pick) {{
          const t = pick.querySelector(".result-ticker");
          if (t) addTicker(t.textContent);
        }}
      }} else if (e.key === "Escape") {{
        closeResults();
      }}
    }});
    search.addEventListener("blur", () => {{
      setTimeout(closeResults, 150);
    }});

    metricSel.addEventListener("change", draw);
    scaleSel.addEventListener("change", draw);

    function moneyFmt(n, currency) {{
      const abs = Math.abs(n);
      const sign = n < 0 ? "-" : "";
      const c = currency || "JPY";
      const sym = c === "USD" ? "$" : (c === "KRW" ? "₩" : "¥");
      if (abs >= 1e12) return sign + sym + (abs / 1e12).toFixed(1) + "T";
      if (abs >= 1e9) return sign + sym + (abs / 1e9).toFixed(1) + "B";
      if (abs >= 1e6) return sign + sym + (abs / 1e6).toFixed(1) + "M";
      return sign + sym + Math.round(abs).toLocaleString();
    }}

    function draw() {{
      const metric = metricSel.value;
      const indexed = scaleSel.value === "indexed";
      const chosen = selected.map(t => byTicker[t]).filter(Boolean);

      const yearMap = new Map();
      for (const c of chosen) {{
        for (const y of (c.trends && c.trends.years) || []) {{
          if (y && y.id && !yearMap.has(y.id)) yearMap.set(y.id, y.short || y.id.slice(0, 4));
        }}
      }}
      const yearIds = Array.from(yearMap.keys()).sort();
      const yearLabels = yearIds.map(id => yearMap.get(id));

      const lines = [];
      for (const c of chosen) {{
        const series = ((c.trends && c.trends.series) || []).find(s => s.id === metric);
        if (!series) continue;
        const byId = {{}};
        const ys = (c.trends.years || []);
        (series.values || []).forEach((v, i) => {{
          if (ys[i]) byId[ys[i].id] = v;
        }});
        let vals = yearIds.map(id => (id in byId ? byId[id] : null));
        if (indexed) {{
          const base = vals.find(v => v != null && v !== 0);
          if (base == null) continue;
          vals = vals.map(v => (v == null ? null : (v / base) * 100));
        }}
        lines.push({{
          ticker: c.ticker,
          name: c.company_en,
          href: c.href,
          values: vals,
        }});
      }}

      legend.innerHTML = "";
      svg.innerHTML = "";
      if (!lines.length || !yearIds.length) {{
        empty.hidden = false;
        empty.textContent = selected.length
          ? "No trend data for this metric on the selected companies."
          : "Search and add a company to start.";
        return;
      }}
      empty.hidden = true;

      const W = 880, H = 340;
      const pad = {{ t: 24, r: 20, b: 48, l: 64 }};
      const plotW = W - pad.l - pad.r;
      const plotH = H - pad.t - pad.b;
      const allNums = lines.flatMap(l => l.values.filter(v => v != null));
      let lo = Math.min(...allNums);
      let hi = Math.max(...allNums);
      if (lo === hi) {{ lo -= 1; hi += 1; }}
      const span = hi - lo;
      lo -= span * 0.08;
      hi += span * 0.08;

      const xAt = (i) => pad.l + (yearIds.length === 1 ? plotW / 2 : (plotW * i) / (yearIds.length - 1));
      const yAt = (v) => pad.t + plotH * (1 - (v - lo) / (hi - lo));

      const ns = "http://www.w3.org/2000/svg";
      function el(name, attrs) {{
        const n = document.createElementNS(ns, name);
        for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
        return n;
      }}

      for (let g = 0; g < 5; g++) {{
        const yy = pad.t + (plotH * g) / 4;
        const val = hi - ((hi - lo) * g) / 4;
        svg.appendChild(el("line", {{
          x1: pad.l, y1: yy, x2: W - pad.r, y2: yy,
          stroke: "#e0d9cb", "stroke-width": "1"
        }}));
        const t = el("text", {{
          x: pad.l - 8, y: yy + 4, "text-anchor": "end",
          fill: "#5c645f", "font-size": "11", "font-family": "IBM Plex Sans, sans-serif"
        }});
        const axisCcy = (chosen[0] && chosen[0].currency) || "JPY";
        t.textContent = indexed ? val.toFixed(0) : moneyFmt(val, axisCcy);
        svg.appendChild(t);
      }}

      yearLabels.forEach((lab, i) => {{
        const t = el("text", {{
          x: xAt(i), y: H - 18, "text-anchor": "middle",
          fill: "#5c645f", "font-size": "12", "font-family": "IBM Plex Sans, sans-serif"
        }});
        t.textContent = lab;
        svg.appendChild(t);
      }});

      lines.forEach((line, li) => {{
        const color = COLORS[li % COLORS.length];
        let seg = [];
        const flush = () => {{
          if (seg.length < 2) {{ seg = []; return; }}
          const d = seg.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ");
          svg.appendChild(el("path", {{
            d, fill: "none", stroke: color, "stroke-width": "2.5",
            "stroke-linecap": "round", "stroke-linejoin": "round"
          }}));
          seg = [];
        }};
        line.values.forEach((v, i) => {{
          if (v == null) {{ flush(); return; }}
          seg.push([xAt(i), yAt(v)]);
        }});
        flush();
        line.values.forEach((v, i) => {{
          if (v == null) return;
          svg.appendChild(el("circle", {{
            cx: xAt(i), cy: yAt(v), r: 3.5, fill: color
          }}));
        }});
        const item = document.createElement("div");
        item.className = "legend-item";
        const a = document.createElement("a");
        a.href = line.href || "#";
        a.textContent = line.name + " (" + line.ticker + ")";
        const sw = document.createElement("span");
        sw.className = "swatch";
        sw.style.background = color;
        item.appendChild(sw);
        item.appendChild(a);
        legend.appendChild(item);
      }});
    }}

    renderChips();
    draw();
  }})();
  </script>
</body>
</html>
"""


def write_index(catalog: list[dict] | None = None) -> Path:
    if catalog is None:
        if CATALOG_PATH.exists():
            catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        else:
            catalog = []
    sync_assets()
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(render_index(catalog), encoding="utf-8")
    COMPARE_PATH.write_text(render_compare(catalog), encoding="utf-8")
    print("Wrote", COMPARE_PATH)
    return INDEX_PATH


def build_one(
    meta: dict,
    zip_path: Path,
    *,
    update_index: bool = True,
    fetch_quote: bool = True,
) -> Path:
    """Parse one filing zip into HTML + catalog/index update."""
    print("Parsing facts…", meta.get("docID"), flush=True)
    facts = parse_facts(zip_path)
    profile = parse_company_profile(zip_path, meta)
    facts_path = FACTS_DIR / f"{meta['docID']}.json"
    period_ends = extract_period_ends(zip_path, meta)
    print("Parsing notes for impairments / one-offs…", flush=True)
    one_offs = parse_one_offs(zip_path, facts)
    analysis = build_analysis(meta, facts, profile, period_ends, one_offs)
    _write_facts_json(
        facts_path,
        meta,
        facts,
        profile,
        analysis.get("one_offs") or one_offs or None,
    )
    print("Wrote", facts_path, flush=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{analysis['ticker']}.html"
    out_path.write_text(render_html(analysis, fetch_quote=fetch_quote), encoding="utf-8")
    print("Wrote", out_path, flush=True)
    catalog = upsert_catalog(analysis)
    if update_index:
        index_path = write_index(catalog)
        print("Wrote", index_path, flush=True)
    return out_path


def sec_fetch_companyfacts(cik: str) -> dict:
    cik_p = str(cik).zfill(10)
    r = requests.get(
        f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_p}.json",
        headers=SEC_HEADERS,
        timeout=120,
    )
    r.raise_for_status()
    return r.json()


def sec_fetch_submissions(cik: str) -> dict:
    cik_p = str(cik).zfill(10)
    r = requests.get(
        f"https://data.sec.gov/submissions/CIK{cik_p}.json",
        headers=SEC_HEADERS,
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def sec_annual_points(fact: dict | None, unit: str = "USD") -> list[dict]:
    """Deduped 10-K FY points, newest end date first."""
    if not fact:
        return []
    rows = (fact.get("units") or {}).get(unit) or []
    by_end: dict[str, dict] = {}
    for e in rows:
        form = e.get("form") or ""
        if form not in ("10-K", "10-K/A"):
            continue
        fp = e.get("fp")
        if fp and fp != "FY":
            continue
        end = e.get("end")
        if not end:
            continue
        prev = by_end.get(end)
        if prev is None or (e.get("filed") or "") >= (prev.get("filed") or ""):
            by_end[end] = e
    return sorted(by_end.values(), key=lambda x: x["end"], reverse=True)


def sec_pick_fact(gaap: dict, keys: list[str]) -> dict | None:
    for k in keys:
        if k in gaap:
            return gaap[k]
    return None


def build_analysis_from_sec(facts: dict, submissions: dict, ticker: str) -> dict:
    """Map SEC companyfacts into the shared analysis shape."""
    global _ACTIVE_CURRENCY
    _ACTIVE_CURRENCY = "USD"

    gaap = (facts.get("facts") or {}).get("us-gaap") or {}
    entity = facts.get("entityName") or submissions.get("name") or ticker
    cik = str(facts.get("cik") or submissions.get("cik") or "").zfill(10)

    def series(keys: list[str], unit: str = "USD") -> list[dict]:
        return sec_annual_points(sec_pick_fact(gaap, keys), unit)

    rev_s = series(
        [
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet",
            "Revenues",
        ]
    )
    op_s = series(["OperatingIncomeLoss"])
    ni_s = series(["NetIncomeLoss"])
    gp_s = series(["GrossProfit"])
    assets_s = series(["Assets"])
    equity_s = series(["StockholdersEquity"])
    cash_s = series(["CashAndCashEquivalentsAtCarryingValue"])
    ca_s = series(["AssetsCurrent"])
    cl_s = series(["LiabilitiesCurrent"])
    liab_s = series(["Liabilities"])
    ocf_s = series(["NetCashProvidedByUsedInOperatingActivities"])
    icf_s = series(["NetCashProvidedByUsedInInvestingActivities"])
    fcf_s = series(["NetCashProvidedByUsedInFinancingActivities"])
    tax_s = series(["IncomeTaxExpenseBenefit"])
    eps_s = series(["EarningsPerShareBasic"], unit="USD/shares")

    def at(points: list[dict], i: int) -> float | None:
        if i < len(points):
            return points[i].get("val")
        return None

    def end_at(points: list[dict], i: int) -> str | None:
        if i < len(points):
            return points[i].get("end")
        return None

    current_end = end_at(rev_s, 0) or end_at(ni_s, 0)
    prior_end = end_at(rev_s, 1) or end_at(ni_s, 1)
    if not current_end:
        raise SystemExit("No annual revenue/income in SEC facts")

    sales = {"cur": at(rev_s, 0), "prior": at(rev_s, 1)}
    op = {"cur": at(op_s, 0), "prior": at(op_s, 1)}
    profit = {"cur": at(ni_s, 0), "prior": at(ni_s, 1)}
    gross = {"cur": at(gp_s, 0), "prior": at(gp_s, 1)}
    assets = {"cur": at(assets_s, 0), "prior": at(assets_s, 1)}
    equity = {"cur": at(equity_s, 0), "prior": at(equity_s, 1)}
    cash = {"cur": at(cash_s, 0), "prior": at(cash_s, 1)}
    ca = {"cur": at(ca_s, 0), "prior": at(ca_s, 1)}
    cl = {"cur": at(cl_s, 0), "prior": at(cl_s, 1)}
    liab = {"cur": at(liab_s, 0), "prior": at(liab_s, 1)}
    ocf = {"cur": at(ocf_s, 0), "prior": at(ocf_s, 1)}
    icf = {"cur": at(icf_s, 0), "prior": at(icf_s, 1)}
    fcf = {"cur": at(fcf_s, 0), "prior": at(fcf_s, 1)}
    tax = {"cur": at(tax_s, 0), "prior": at(tax_s, 1)}
    eps = {"cur": at(eps_s, 0), "prior": at(eps_s, 1)}

    def cos(side: str) -> float | None:
        s, g = sales[side], gross[side]
        if s is None or g is None:
            return None
        return s - g

    def ncl(side: str) -> float | None:
        t, c = liab[side], cl[side]
        if t is None or c is None:
            return None
        return t - c

    def nca(side: str) -> float | None:
        a, c = assets[side], ca[side]
        if a is None or c is None:
            return None
        return a - c

    years = []
    if prior_end:
        years.append(
            {
                "id": prior_end,
                "label": fiscal_year_label(prior_end),
                "key": "prior",
            }
        )
    years.append(
        {
            "id": current_end,
            "label": fiscal_year_label(current_end),
            "key": "cur",
        }
    )

    income_statement = [
        {"label": "Revenue", "prior": sales["prior"], "cur": sales["cur"]},
        {"label": "Cost of sales*", "prior": cos("prior"), "cur": cos("cur")},
        {"label": "Gross profit", "prior": gross["prior"], "cur": gross["cur"]},
        {"label": "Operating profit", "prior": op["prior"], "cur": op["cur"], "total": True},
        {"label": "Income tax", "prior": tax["prior"], "cur": tax["cur"]},
        {"label": "Net income", "prior": profit["prior"], "cur": profit["cur"], "total": True},
        {"label": "Basic EPS", "prior": eps["prior"], "cur": eps["cur"], "kind": "eps"},
    ]
    balance_sheet = [
        {"label": "Cash & equivalents", "prior": cash["prior"], "cur": cash["cur"]},
        {"label": "Current assets", "prior": ca["prior"], "cur": ca["cur"]},
        {"label": "Non-current assets*", "prior": nca("prior"), "cur": nca("cur")},
        {"label": "Total assets", "prior": assets["prior"], "cur": assets["cur"], "total": True},
        {"label": "Current liabilities", "prior": cl["prior"], "cur": cl["cur"]},
        {"label": "Non-current liabilities*", "prior": ncl("prior"), "cur": ncl("cur")},
        {"label": "Total liabilities", "prior": liab["prior"], "cur": liab["cur"], "total": True},
        {"label": "Stockholders’ equity", "prior": equity["prior"], "cur": equity["cur"], "total": True},
    ]
    cash_flow = [
        {"label": "Operating cash flow", "prior": ocf["prior"], "cur": ocf["cur"], "total": True},
        {"label": "Investing cash flow", "prior": icf["prior"], "cur": icf["cur"]},
        {"label": "Financing cash flow", "prior": fcf["prior"], "cur": fcf["cur"]},
        {"label": "Cash at end of period", "prior": cash["prior"], "cur": cash["cur"], "total": True},
    ]

    # Trends: align last TREND_YEARS by end date from revenue series
    ends = [p["end"] for p in rev_s[:TREND_YEARS]]
    ends = list(reversed(ends))  # oldest → newest

    def vals_for(points: list[dict]) -> list[float | None]:
        by_end = {p["end"]: p.get("val") for p in points}
        return [by_end.get(e) for e in ends]

    year_meta = [
        {
            "id": e,
            "short": f"FY{e[:4]}" if len(e) >= 4 else e,
            "label": fiscal_year_label(e),
        }
        for e in ends
    ]
    trends = {
        "years": year_meta,
        "series": [
            {"id": "revenue", "label": "Revenue", "values": vals_for(rev_s)},
            {"id": "operating_profit", "label": "Operating profit", "values": vals_for(op_s)},
            {"id": "profit_owners", "label": "Net income", "values": vals_for(ni_s)},
            {"id": "total_assets", "label": "Total assets", "values": vals_for(assets_s)},
            {"id": "cash", "label": "Cash & equivalents", "values": vals_for(cash_s)},
            {"id": "equity_owners", "label": "Stockholders’ equity", "values": vals_for(equity_s)},
        ],
        "max_years": TREND_YEARS,
    }
    trends["series"] = [s for s in trends["series"] if any(v is not None for v in s["values"])]

    if (
        op["cur"] is not None
        and op["prior"] is not None
        and op["cur"] > 0
        and sales["cur"]
        and sales["prior"]
        and sales["cur"] > sales["prior"]
    ):
        verdict = "Constructive"
        headline = "Sales and operating profit both moved in a healthier direction."
    elif op["cur"] is not None and op["prior"] is not None and op["cur"] < 0 < (op["prior"] or 0):
        verdict = "Challenged"
        headline = (
            "Profitability turned negative — read cash flow and notes before treating it as a cash problem."
        )
    else:
        verdict = "Mixed"
        headline = (
            "The numbers send mixed signals — dig into cash flow and leverage before drawing a conclusion."
        )

    if ticker == "AAPL":
        about = (
            "Apple Inc. designs and sells consumer electronics, software, and services, including the iPhone, "
            "Mac, iPad, Wearables, and a growing Services segment (App Store, advertising, cloud, and more). "
            "Results are reported under US GAAP on a consolidated basis."
        )
        products = ["iPhone", "Mac", "iPad", "Wearables & accessories", "Services"]
        segments = ["iPhone", "Mac", "iPad", "Wearables, Home and Accessories", "Services"]
    else:
        about = (
            f"{entity} is a US-listed company with consolidated financial statements filed on SEC EDGAR."
        )
        products, segments = [], []

    analysis_paras = [
        (
            f"On the income statement, revenue moved from {yen(sales['prior'])} to {yen(sales['cur'])} "
            f"({yoy(sales['cur'], sales['prior'])}). "
            f"Operating profit went from {yen(op['prior'])} to {yen(op['cur'])} "
            f"({yoy(op['cur'], op['prior'])})."
        ),
        (
            f"Operating cash flow was {yen(ocf['cur'])} (prior {yen(ocf['prior'])}), with cash on the balance sheet "
            f"at {yen(cash['cur'])} versus {yen(cash['prior'])}."
        ),
    ]

    recent = (submissions.get("filings") or {}).get("recent") or {}
    accession = None
    forms = recent.get("form") or []
    accessions = recent.get("accessionNumber") or []
    for form, acc in zip(forms, accessions):
        if form in ("10-K", "10-K/A"):
            accession = acc
            break
    source_url = (
        f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-K"
    )

    filed = None
    for form, fdate in zip(forms, recent.get("filingDate") or []):
        if form in ("10-K", "10-K/A"):
            filed = fdate
            break

    return {
        "meta": {
            "date": filed,
            "secCode": ticker,
            "filerName": entity,
            "docID": accession or f"CIK{cik}",
            "docDescription": "Form 10-K (annual report)",
            "periodEnd": current_end,
            "edinetCode": cik,
        },
        "ticker": ticker,
        "company_en": company_en_name(
            ticker,
            entity if entity.endswith("Inc.") or "Inc" in entity else entity,
        ),
        "market": "US",
        "currency": "USD",
        "verdict": verdict,
        "headline": headline,
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "about": {
            "summary": about,
            "products": products,
            "segments": segments,
        },
        "ir_en_url": IR_EN_URLS.get(ticker),
        "contacts": {
            "phone": (submissions.get("phones") or [None])[0]
            if isinstance(submissions.get("phones"), list)
            else submissions.get("phone"),
            "email": None,
            "as_of": filed,
            "source": "SEC EDGAR submissions",
        },
        "periods": {
            "max_years": MAX_YEARS,
            "current_end": current_end,
            "prior_end": prior_end,
            "years": years,
            "default_focus": current_end,
        },
        "statements": {
            "income": income_statement,
            "balance": balance_sheet,
            "cashflow": cash_flow,
        },
        "trends": trends,
        "one_offs": {
            "items": [],
            "by_segment": [],
            "drivers": [],
            "confidence": {
                "level": "medium",
                "label": "From SEC",
            },
        },
        "analysis_paras": analysis_paras,
        "checks": [
            {
                "title": "Earnings quality",
                "body": "Compare earnings and operating cash flow for earnings quality.",
            },
            {
                "title": "Liquidity & leverage",
                "body": f"Cash moved from {yen(cash['prior'])} to {yen(cash['cur'])}; "
                f"current liabilities {yen(cl['cur'])}.",
            },
            {
                "title": "Capital buffer",
                "body": f"Stockholders’ equity moved from {yen(equity['prior'])} to {yen(equity['cur'])}.",
            },
        ],
        "source_url": source_url,
    }


def build_us_company(
    ticker: str = "AAPL",
    *,
    update_index: bool = True,
    fetch_quote: bool = True,
    force: bool = False,
) -> Path:
    """Fetch one US issuer from SEC EDGAR companyfacts and write HTML + catalog."""
    t = ticker.strip().upper()
    cik = SEC_CIKS.get(t)
    if not cik:
        raise SystemExit(f"Unknown ticker {t}. Add it to SEC_CIKS (e.g. AAPL, MSFT).")
    FACTS_DIR.mkdir(parents=True, exist_ok=True)
    facts_path = FACTS_DIR / f"SEC-{t}.json"
    cache_path = FACTS_DIR / f"SEC-{t}-companyfacts.json"
    sub_path = FACTS_DIR / f"SEC-{t}-submissions.json"

    if not force and (OUT_DIR / f"{t}.html").exists() and facts_path.exists():
        print("SKIP US", t, "(already built; pass force=True to rebuild)", flush=True)
        return OUT_DIR / f"{t}.html"

    print("SEC EDGAR companyfacts…", t, cik, flush=True)
    if not force and cache_path.exists() and sub_path.exists():
        facts = json.loads(cache_path.read_text(encoding="utf-8"))
        submissions = json.loads(sub_path.read_text(encoding="utf-8"))
        print("  using cached SEC JSON", flush=True)
    else:
        facts = sec_fetch_companyfacts(cik)
        submissions = sec_fetch_submissions(cik)
        cache_path.write_text(json.dumps(facts), encoding="utf-8")
        sub_path.write_text(json.dumps(submissions), encoding="utf-8")
    print("Selected:", facts.get("entityName"), t, flush=True)

    analysis = build_analysis_from_sec(facts, submissions, t)
    slim_trends = analysis.get("trends")
    facts_path.write_text(
        json.dumps(
            {
                "meta": analysis["meta"],
                "market": "US",
                "ticker": t,
                "entityName": facts.get("entityName"),
                "cik": cik,
                "trends": slim_trends,
                "one_offs": analysis.get("one_offs"),
                "profile": analysis.get("about"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("Wrote", facts_path, flush=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{analysis['ticker']}.html"
    out_path.write_text(render_html(analysis, fetch_quote=fetch_quote), encoding="utf-8")
    print("Wrote", out_path, flush=True)
    catalog = upsert_catalog(analysis)
    if update_index:
        write_index(catalog)
    return out_path


def resolve_dart_corp_code(stock_code: str) -> str | None:
    """Look up Open DART corp_code from built-in map or cached JSON."""
    code = stock_code.strip().zfill(6)
    if code in DART_CORP_CODES:
        return DART_CORP_CODES[code]
    cache = ROOT / "data" / "dart_corp_codes.json"
    if cache.exists():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            hit = data.get(code)
            if isinstance(hit, dict) and hit.get("corp_code"):
                return str(hit["corp_code"])
            if isinstance(hit, str):
                return hit
        except json.JSONDecodeError:
            pass
    return None


def build_kr_company(
    stock_code: str = "005930",
    year: int = 2024,
    *,
    update_index: bool = True,
    fetch_quote: bool = True,
    force: bool = False,
) -> Path:
    """Fetch one Korea issuer from Open DART and write HTML + catalog."""
    key = load_opendart_key()
    code = stock_code.strip().zfill(6)
    corp_code = resolve_dart_corp_code(code)
    if not corp_code:
        raise SystemExit(
            f"Unknown stock_code {code}. Add it to DART_CORP_CODES or pass a mapped issuer."
        )
    FACTS_DIR.mkdir(parents=True, exist_ok=True)
    facts_path = FACTS_DIR / f"DART-{code}-{year}.json"
    out_path = OUT_DIR / f"{code}.html"
    if not force and out_path.exists() and facts_path.exists():
        print("SKIP KR", code, "(already built; pass force=True to rebuild)", flush=True)
        return out_path

    print("Open DART company…", code, corp_code, flush=True)
    company = dart_fetch_company(key, corp_code)
    print("Selected:", company.get("corp_name"), company.get("stock_code"), flush=True)

    years = list(range(year - TREND_YEARS + 1, year + 1))
    print(f"Fetching FY{years[0]}–{year} statements (parallel)…", flush=True)

    def fetch_year(y: int) -> tuple[int, list[dict] | None, str | None]:
        try:
            return y, dart_fetch_statements(key, corp_code, y), None
        except Exception as e:
            return y, None, str(e)

    by_year_rows: dict[int, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=min(5, len(years))) as pool:
        for y, yrows, err in pool.map(fetch_year, years):
            if err or yrows is None:
                print("  skip", y, err, flush=True)
                continue
            print(f"  trend year {y}: {len(yrows)} rows", flush=True)
            by_year_rows[y] = yrows

    rows = by_year_rows.get(year) or []
    if not rows:
        raise SystemExit(f"No DART statements for {code} FY{year}")

    trend_by_year: dict[int, dict[str, float | None]] = {}
    for y, yrows in by_year_rows.items():

        def g(names: list[str], sj: str | None = None, _rows=yrows) -> float | None:
            row = dart_find_account(_rows, names, sj)
            return _dart_amt(row.get("thstrm_amount")) if row else None

        trend_by_year[y] = {
            "revenue": g(["매출액", "수익(매출액)"], "IS") or g(["매출액"]),
            "operating_profit": g(["영업이익"], "IS") or g(["영업이익"]),
            "profit_owners": g(["당기순이익"], "IS") or g(["당기순이익"]),
            "total_assets": g(["자산총계"], "BS") or g(["자산총계"]),
            "cash": g(["현금및현금성자산"], "BS") or g(["현금및현금성자산"]),
            "equity_owners": g(["자본총계"], "BS") or g(["자본총계"]),
        }

    analysis = build_analysis_from_dart(company, rows, year, trend_by_year)
    facts_path.write_text(
        json.dumps(
            {
                "meta": analysis["meta"],
                "market": "KR",
                "company": company,
                "year": year,
                "trends": trend_by_year,
                "one_offs": analysis.get("one_offs"),
                "profile": analysis.get("about"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("Wrote", facts_path, flush=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{analysis['ticker']}.html"
    out_path.write_text(render_html(analysis, fetch_quote=fetch_quote), encoding="utf-8")
    print("Wrote", out_path, flush=True)
    catalog = upsert_catalog(analysis)
    if update_index:
        write_index(catalog)
    return out_path


def _cli_nonneg_limit(flag: str, *, env_key: str) -> int | None:
    """Parse --flag N or ENV; None means unlimited (all missing)."""
    import os
    import sys

    if flag in sys.argv:
        idx = sys.argv.index(flag)
        if idx + 1 >= len(sys.argv) or sys.argv[idx + 1].startswith("-"):
            raise SystemExit(f"{flag} requires a non-negative integer")
        try:
            return max(0, int(sys.argv[idx + 1]))
        except ValueError as e:
            raise SystemExit(f"{flag} requires a non-negative integer") from e
    raw = os.environ.get(env_key, "").strip()
    if raw == "":
        return None
    try:
        return max(0, int(raw))
    except ValueError as e:
        raise SystemExit(f"{env_key} must be a non-negative integer") from e


def _apply_market_limit(tickers: list[str], limit: int | None, market: str) -> list[str]:
    if limit is None:
        return tickers
    if limit <= 0:
        if tickers:
            print(f"Universe {market}: limit 0 — skip {len(tickers)} missing", flush=True)
        return []
    if len(tickers) > limit:
        print(
            f"Universe {market}: building {limit}/{len(tickers)} missing",
            flush=True,
        )
        return tickers[:limit]
    return tickers


def main() -> None:
    import sys

    if "--index" in sys.argv:
        path = write_index()
        print("Wrote", path)
        return

    if "--kr" in sys.argv:
        idx = sys.argv.index("--kr")
        code = sys.argv[idx + 1] if idx + 1 < len(sys.argv) and not sys.argv[idx + 1].startswith("-") else "005930"
        year = 2024
        if "--year" in sys.argv:
            yi = sys.argv.index("--year")
            year = int(sys.argv[yi + 1])
        build_kr_company(code, year)
        return

    if "--us" in sys.argv:
        idx = sys.argv.index("--us")
        code = (
            sys.argv[idx + 1]
            if idx + 1 < len(sys.argv) and not sys.argv[idx + 1].startswith("-")
            else "AAPL"
        )
        build_us_company(code)
        return

    if "--rebuild-all" in sys.argv or "--refresh-all" in sys.argv:
        # Rebuild every cached zip → HTML + catalog + compare (index once at end)
        zips = sorted(RAW_DIR.glob("*.zip"))
        if not zips:
            raise SystemExit("No zip files in data/raw")
        for zip_path in zips:
            doc_id = zip_path.stem
            facts_path = FACTS_DIR / f"{doc_id}.json"
            if facts_path.exists():
                meta = json.loads(facts_path.read_text(encoding="utf-8"))["meta"]
            else:
                meta = {"docID": doc_id, "secCode": "", "filerName": doc_id, "date": None}
            print("Rebuilding", doc_id, meta.get("filerName"), flush=True)
            build_one(meta, zip_path, update_index=False, fetch_quote=False)
        if "--refresh-all" in sys.argv:
            try:
                build_kr_company("005930", 2024, update_index=False, fetch_quote=False)
            except Exception as e:
                print("KR refresh skipped:", e, flush=True)
            try:
                build_us_company("AAPL", update_index=False, fetch_quote=False)
            except Exception as e:
                print("US refresh skipped:", e, flush=True)
        write_index()
        return

    if "--universe" in sys.argv:
        # Build JP + KR + US. Optimized:
        # - skip tickers that already have pages (unless --force)
        # - EDINET-scan only missing JP names
        # - defer index/compare to a single write at the end
        # - skip live quotes during batch
        # - parallel KR year fetches + parallel KR/US companies
        force = "--force" in sys.argv
        ok, fail, skipped = [], [], []
        have = catalog_tickers() if not force else set()

        jp_limit = _cli_nonneg_limit("--jp-limit", env_key="COMPANYDB_JP_LIMIT")
        kr_limit = _cli_nonneg_limit("--kr-limit", env_key="COMPANYDB_KR_LIMIT")
        us_limit = _cli_nonneg_limit("--us-limit", env_key="COMPANYDB_US_LIMIT")

        need_jp = [t for t in UNIVERSE_JP if force or t not in have]
        need_kr = [t for t in UNIVERSE_KR if force or t not in have]
        need_us = [t for t in UNIVERSE_US if force or t not in have]
        for t in UNIVERSE_JP + UNIVERSE_KR + UNIVERSE_US:
            if t not in need_jp and t not in need_kr and t not in need_us:
                skipped.append(t)

        need_jp = _apply_market_limit(need_jp, jp_limit, "JP")
        need_kr = _apply_market_limit(need_kr, kr_limit, "KR")
        need_us = _apply_market_limit(need_us, us_limit, "US")

        print(
            f"Universe: need JP {len(need_jp)}/{len(UNIVERSE_JP)}, "
            f"KR {len(need_kr)}/{len(UNIVERSE_KR)}, US {len(need_us)}/{len(UNIVERSE_US)}; "
            f"skip {len(skipped)} (use --force to rebuild)"
            + (
                f"; limits jp={jp_limit} kr={kr_limit} us={us_limit}"
                if any(x is not None for x in (jp_limit, kr_limit, us_limit))
                else ""
            ),
            flush=True,
        )

        # Japan via EDINET
        if need_jp:
            key = load_api_key()
            print(f"EDINET scan for {len(need_jp)} JP tickers…", flush=True)
            metas = find_annual_reports_for_secs(key, need_jp)
            for sec in sorted(metas):
                meta = metas[sec]
                ticker = meta["secCode"][:4] if len(meta["secCode"]) == 5 else meta["secCode"]
                try:
                    print("JP", meta["secCode"], meta["filerName"], meta["docID"], flush=True)
                    zip_path = download_xbrl_zip(key, meta["docID"])
                    build_one(
                        meta,
                        zip_path,
                        update_index=False,
                        fetch_quote=False,
                    )
                    ok.append(ticker)
                except Exception as e:
                    print("FAIL JP", meta.get("secCode"), e, flush=True)
                    fail.append(("JP", meta.get("secCode"), str(e)))
            for sec in need_jp:
                norm = _normalize_sec(sec)
                if norm not in metas and sec not in ok:
                    fail.append(("JP", sec, "no annual report in scan window"))

        # Korea via Open DART (parallel companies; each fetches years in parallel)
        if need_kr:
            print(f"Universe KR ({len(need_kr)}) parallel…", flush=True)

            def _kr(code: str) -> tuple[str, str | None]:
                try:
                    build_kr_company(
                        code,
                        2024,
                        update_index=False,
                        fetch_quote=False,
                        force=force,
                    )
                    return code, None
                except Exception as e:
                    return code, str(e)

            with ThreadPoolExecutor(max_workers=4) as pool:
                futs = {pool.submit(_kr, c): c for c in need_kr}
                for fut in as_completed(futs):
                    code, err = fut.result()
                    if err:
                        print("FAIL KR", code, err, flush=True)
                        fail.append(("KR", code, err))
                    else:
                        print("OK KR", code, flush=True)
                        ok.append(code)

        # US via SEC (parallel; uses on-disk companyfacts cache)
        if need_us:
            print(f"Universe US ({len(need_us)}) parallel…", flush=True)

            def _us(t: str) -> tuple[str, str | None]:
                try:
                    build_us_company(
                        t,
                        update_index=False,
                        fetch_quote=False,
                        force=force,
                    )
                    return t, None
                except Exception as e:
                    return t, str(e)

            with ThreadPoolExecutor(max_workers=4) as pool:
                futs = {pool.submit(_us, t): t for t in need_us}
                for fut in as_completed(futs):
                    t, err = fut.result()
                    if err:
                        print("FAIL US", t, err, flush=True)
                        fail.append(("US", t, err))
                    else:
                        print("OK US", t, flush=True)
                        ok.append(t)

        write_index()
        print(
            f"Universe done. ok={len(ok)} skip={len(skipped)} fail={len(fail)}",
            flush=True,
        )
        for row in fail:
            print(" ", row, flush=True)
        return

    if "--secs" in sys.argv:
        idx = sys.argv.index("--secs")
        if idx + 1 >= len(sys.argv):
            raise SystemExit("Usage: build_company_page.py --secs 7203,6758,7974")
        secs = [s.strip() for s in sys.argv[idx + 1].split(",") if s.strip()]
        key = load_api_key()
        print("Finding annual reports for", secs)
        metas = find_annual_reports_for_secs(key, secs)
        for sec in sorted(metas):
            meta = metas[sec]
            print("Selected:", meta["secCode"], meta["filerName"], meta["docID"])
            print("Downloading XBRL…")
            zip_path = download_xbrl_zip(key, meta["docID"])
            build_one(meta, zip_path)
        return

    # Rebuild from cached zip/facts: python3 script/build_company_page.py --local [docID]
    cached_one_offs: dict = {}
    if "--local" in sys.argv:
        args = [a for a in sys.argv[1:] if a != "--local"]
        doc_id = args[0] if args else "S100Z5CA"
        facts_path = FACTS_DIR / f"{doc_id}.json"
        zip_path = RAW_DIR / f"{doc_id}.zip"
        profile = {}
        if zip_path.exists():
            print("Parsing cached XBRL…", zip_path)
            facts = parse_facts(zip_path)
            meta = json.loads(facts_path.read_text())["meta"] if facts_path.exists() else {
                "docID": doc_id,
                "secCode": "65940",
                "filerName": "ニデック株式会社",
                "docDescription": "有価증권報告書",
                "periodEnd": "2026-03-31",
                "date": "2026-09-30",
            }
            profile = parse_company_profile(zip_path, meta)
        elif facts_path.exists():
            packed = json.loads(facts_path.read_text())
            meta, facts = packed["meta"], packed["facts"]
            profile = packed.get("profile") or {}
            cached_one_offs = packed.get("one_offs") or {}
        else:
            raise SystemExit(f"No cache for {doc_id}")
    else:
        key = load_api_key()
        target_sec = None
        if "--sec" in sys.argv:
            idx = sys.argv.index("--sec")
            if idx + 1 >= len(sys.argv):
                raise SystemExit("Usage: build_company_page.py --sec 7203")
            target_sec = sys.argv[idx + 1]
        print("Finding annual report…", f"(sec={target_sec})" if target_sec else "")
        meta = find_annual_report(key, target_sec=target_sec)
        print("Selected:", meta["secCode"], meta["filerName"], meta["docID"])
        print("Downloading XBRL…")
        zip_path = download_xbrl_zip(key, meta["docID"])
        print("Parsing facts…")
        facts = parse_facts(zip_path)
        profile = parse_company_profile(zip_path, meta)
        facts_path = FACTS_DIR / f"{meta['docID']}.json"

    zip_for_periods = RAW_DIR / f"{meta.get('docID')}.zip"
    period_ends = extract_period_ends(
        zip_for_periods if zip_for_periods.exists() else None,
        meta,
    )
    one_offs: dict = {}
    if zip_for_periods.exists():
        print("Parsing notes for impairments / one-offs…")
        one_offs = parse_one_offs(zip_for_periods, facts)
    elif cached_one_offs:
        print("Using cached one_offs from facts JSON…")
        one_offs = cached_one_offs

    analysis = build_analysis(meta, facts, profile, period_ends, one_offs)
    _write_facts_json(
        facts_path,
        meta,
        facts,
        profile,
        analysis.get("one_offs") or one_offs or None,
    )
    print("Wrote", facts_path)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{analysis['ticker']}.html"
    out_path.write_text(render_html(analysis), encoding="utf-8")
    print("Wrote", out_path)

    catalog = upsert_catalog(analysis)
    index_path = write_index(catalog)
    print("Wrote", index_path)


if __name__ == "__main__":
    main()
