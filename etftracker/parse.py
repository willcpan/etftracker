"""Turn a downloaded holdings file (CSV / XLSX / HTML table) into normalized Holdings.

Fund administrators publish wildly different layouts, so this module works in two
stages: first get a list of rows (list[dict]) with the header row detected
heuristically, then map header names onto our normalized fields using a
synonym table (overridable per fund via ``columns`` in funds.yaml).
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date

from bs4 import BeautifulSoup

from .models import Holding
from .util import parse_date, to_float

# normalized field -> header synonyms (lowercase, punctuation stripped)
SYNONYMS: dict[str, list[str]] = {
    "ticker": ["ticker", "stockticker", "symbol", "tickersymbol", "security ticker", "holding ticker", "tkr"],
    "name": [
        "name", "security name", "securityname", "security", "description", "security description",
        "holding", "holdings", "company", "company name", "issuer", "issuer name", "security_name",
    ],
    "cusip": ["cusip", "security identifier", "identifier", "security id"],
    "isin": ["isin"],
    "sedol": ["sedol"],
    "shares": [
        "shares", "share", "quantity", "qty", "shares held", "sharesheld", "units", "par value",
        "shares/par", "shares par value", "principal", "shares or principal", "sharespar",
        "shares quantity", "number of shares", "nominal",
    ],
    "price": ["price", "market price", "last price", "close", "closing price", "px", "local price"],
    "market_value": [
        "market value", "marketvalue", "market value ($)", "mv", "value", "market value usd",
        "notional value", "base market value", "total market value", "market val",
    ],
    "weight": [
        "weight", "weight (%)", "weightings", "weighting", "% of net assets", "percent of net assets",
        "net assets %", "net assets percent", "percentage of net assets", "% net asset value",
        "pct of net assets", "% net assets", "% of fund", "% of portfolio", "portfolio weight",
        "% weight", "weight %", "percentage", "% of assets", "allocation", "% of nav", "pct", "% tna",
        "percent", "percent of fund", "net assets %", "% of total", "% of total net assets",
    ],
    "asset_type": ["asset class", "assetclass", "asset type", "security type", "type", "sector type"],
    "cash_flag": ["moneymarketflag", "money market flag", "cash flag", "is cash"],
    "net_assets": ["net assets", "netassets", "total net assets", "fund net assets"],
    "currency": ["currency", "ccy", "local currency"],
    "date": ["date", "as of", "as of date", "asofdate", "holdings date", "effective date", "trade date"],
    "account": ["account", "fund", "fund name", "fund ticker", "portfolio"],
}

CASH_RE = re.compile(
    r"\b(cash|money market|mmkt|treasury bill|t-bill|tbill|us treasury|treasury trust|treasury fund|deposit|repo|repurchase|"
    r"liquidity|sweep|fgxxx|government obligations|first american|dreyfus|invesco government|"
    r"other assets|net other|payable|receivable|accrued|futures|forward)",
    re.IGNORECASE,
)
CASH_TICKERS = {"CASH", "USD", "FGXXX", "FGTXX", "X9USDBLDP", "CASH_USD", "USD CASH", "DGCXX", "TFDXX", "SGOV", "BIL"}


def _norm_header(h) -> str:
    s = str(h or "").strip().lower()
    s = s.replace("\n", " ").replace("_", " ")
    s = re.sub(r"\s+", " ", s)
    return s


def _header_score(cells: list[str]) -> int:
    """How much does this row look like a header? Count cells matching any synonym."""
    flat = {syn for syns in SYNONYMS.values() for syn in syns}
    n = 0
    for c in cells:
        c = _norm_header(c)
        if c in flat or any(c.startswith(s) or c.endswith(s) for s in ("ticker", "symbol", "shares", "weight", "cusip", "market value")):
            n += 1
    return n


def rows_from_matrix(matrix: list[list[str]]) -> tuple[list[dict], list[str], list[str]]:
    """Given a 2-D table (list of rows of strings), find the header row and return
    (rows_as_dicts, header, preamble_lines). Preamble lines (text above the header,
    such as "Holdings as of 10/23/2026") are returned for as-of-date detection."""
    best_i, best_score = None, 0
    for i, row in enumerate(matrix[:40]):
        score = _header_score([c for c in row if c])
        if score > best_score:
            best_i, best_score = i, score
    if best_i is None or best_score < 2:
        raise ValueError("could not locate a header row in holdings table")
    header = [_norm_header(c) for c in matrix[best_i]]
    preamble = [" ".join(c for c in r if c) for r in matrix[:best_i]]
    rows = []
    for r in matrix[best_i + 1 :]:
        if not any(str(c).strip() for c in r):
            continue
        d = {}
        for j, h in enumerate(header):
            if not h:
                continue
            d[h] = r[j].strip() if j < len(r) and r[j] is not None else ""
        rows.append(d)
    return rows, header, preamble


def matrix_from_csv(text: str) -> list[list[str]]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    return [[(c or "").strip() for c in row] for row in reader]


def matrix_from_xlsx(data: bytes) -> list[list[str]]:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    out = []
    for row in ws.iter_rows(values_only=True):
        cells = []
        for c in row:
            if c is None:
                cells.append("")
            elif hasattr(c, "strftime"):
                cells.append(c.strftime("%Y-%m-%d"))
            else:
                cells.append(str(c).strip())
        out.append(cells)
    return out


def matrices_from_html(html: str) -> list[tuple[list[list[str]], str]]:
    """Return every <table> as a matrix plus the text immediately preceding it."""
    soup = BeautifulSoup(html, "lxml")
    results = []
    for table in soup.find_all("table"):
        matrix = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if cells:
                matrix.append(cells)
        # context: caption + previous few text nodes
        context = table.caption.get_text(" ", strip=True) if table.caption else ""
        prev = table.find_previous(string=re.compile(r"\d"))
        if prev:
            context += " " + str(prev)
        results.append((matrix, context))
    return results


def decode_text(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def sniff_kind(data: bytes, content_type: str | None, url: str | None) -> str:
    ct = (content_type or "").lower()
    u = (url or "").lower().split("?")[0]
    if data[:4] == b"PK\x03\x04" or "spreadsheetml" in ct or u.endswith(".xlsx"):
        return "xlsx"
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" or u.endswith(".xls"):
        return "xls"
    head = data[:2048].lstrip().lower()
    if head.startswith((b"<!doctype", b"<html", b"<table")) or "html" in ct:
        return "html"
    return "csv"


def load_matrix(data: bytes, content_type: str | None = None, url: str | None = None,
                table_pattern: str | None = None) -> tuple[list[list[str]], str]:
    """Return (matrix, context_text) from raw bytes of any supported format."""
    kind = sniff_kind(data, content_type, url)
    if kind == "xlsx":
        return matrix_from_xlsx(data), ""
    if kind == "xls":
        raise ValueError("legacy .xls files are not supported; configure an XLSX/CSV source")
    if kind == "html":
        tables = matrices_from_html(decode_text(data))
        if not tables:
            raise ValueError("no <table> found in HTML")
        pat = re.compile(table_pattern, re.IGNORECASE) if table_pattern else None
        best = None
        for matrix, ctx in tables:
            if not matrix:
                continue
            if pat and not any(pat.search(" ".join(r)) for r in matrix[:3]):
                continue
            score = max((_header_score(r) for r in matrix[:5]), default=0)
            if best is None or score > best[0] or (score == best[0] and len(matrix) > len(best[1])):
                best = (score, matrix, ctx)
        if best is None:
            raise ValueError("no matching holdings table in HTML")
        return best[1], best[2]
    return matrix_from_csv(decode_text(data)), ""


def _pick(row: dict, field: str, overrides: dict[str, str]) -> str | None:
    if field in overrides:
        col = _norm_header(overrides[field])
        if col in row:
            return row[col]
        # The configured column is absent (publisher changed the layout): fall back to heuristics.
    for syn in SYNONYMS.get(field, []):
        if syn in row:
            return row[syn]
    # looser: header containing the synonym as a whole word
    for h, v in row.items():
        for syn in SYNONYMS.get(field, []):
            if re.search(rf"(^|\W){re.escape(syn)}($|\W)", h):
                return v
    return None


def clean_ticker(raw: str | None) -> str | None:
    """'AMZN US' -> 'AMZN'; keep foreign exchange codes ('CSU CN', 'RR/ LN'); None if empty."""
    if not raw:
        return None
    t = " ".join(str(raw).upper().split())
    t = re.sub(r"\s+(US|UW|UN|UQ|UA|UR)$", "", t)  # Bloomberg US exchange suffixes
    return t or None


def classify_asset(ticker: str | None, name: str, asset_type_raw: str | None, cash_flag: str | None = None) -> str:
    t = (ticker or "").upper().strip()
    at = (asset_type_raw or "").lower()
    if cash_flag and str(cash_flag).strip().upper() in {"Y", "YES", "TRUE", "1"}:
        return "cash"
    if t in CASH_TICKERS or t.replace("&", "").replace(" ", "") in {"CASHOTHER", "CASHANDOTHER"}:
        return "cash"
    if at and re.search(r"cash|money market|short.?term|treasur|repo|currency", at):
        return "cash"
    if at and re.search(r"equity|stock|common|adr|reit|preferred", at):
        return "equity"
    if CASH_RE.search(name or "") and not re.search(r"\b(inc|corp|co|ltd|plc|holdings|group)\b", (name or "").lower()):
        return "cash"
    if at and re.search(r"bond|note|debt|fixed|option|swap|future|warrant", at):
        return "other"
    return "equity"


def normalize_rows(rows: list[dict], overrides: dict[str, str] | None = None,
                   options: dict | None = None) -> list[Holding]:
    overrides = overrides or {}
    options = options or {}
    holdings: list[Holding] = []
    weights: list[float | None] = []
    net_assets: float | None = None
    for row in rows:
        name = (_pick(row, "name", overrides) or "").strip()
        ticker = clean_ticker(_pick(row, "ticker", overrides))
        if not name and not ticker:
            continue
        if re.match(r"^(total|grand total|net assets|holdings|as of)", name.lower()):
            continue
        h = Holding(
            ticker=ticker,
            name=name or ticker or "",
            cusip=(_pick(row, "cusip", overrides) or "").strip() or None,
            isin=(_pick(row, "isin", overrides) or "").strip() or None,
            sedol=(_pick(row, "sedol", overrides) or "").strip() or None,
            shares=to_float(_pick(row, "shares", overrides)),
            price=to_float(_pick(row, "price", overrides)),
            market_value=to_float(_pick(row, "market_value", overrides)),
            weight=to_float(_pick(row, "weight", overrides)),
        )
        h.asset_type = classify_asset(h.ticker, h.name, _pick(row, "asset_type", overrides),
                                      _pick(row, "cash_flag", overrides))
        if net_assets is None:
            net_assets = to_float(_pick(row, "net_assets", overrides))
        holdings.append(h)
        weights.append(h.weight)
    # Weights may be given in percent (sum ~100) or fractions (sum ~1). Normalize to fractions.
    known = [w for w in weights if w is not None]
    if known and sum(abs(w) for w in known) > 1.5:
        for h in holdings:
            if h.weight is not None:
                h.weight = h.weight / 100.0
    # Derive weight from market value if absent.
    if known == [] or all(w is None for w in weights):
        mvs = [h.market_value for h in holdings if h.market_value is not None]
        total = sum(mvs) if mvs else 0
        if total > 0:
            for h in holdings:
                if h.market_value is not None:
                    h.weight = h.market_value / total
    # Derive market value if absent but shares and price exist, or from weight x net assets.
    for h in holdings:
        if h.market_value is None and h.shares is not None and h.price is not None:
            h.market_value = h.shares * h.price
        if h.market_value is None and options.get("market_value_from_weight") and net_assets and h.weight is not None:
            h.market_value = h.weight * net_assets
        if h.price is None and h.market_value is not None and h.shares:
            h.price = h.market_value / h.shares
    return holdings


def detect_as_of(rows: list[dict], preamble: list[str], context: str, filename: str | None,
                 pattern: str | None = None) -> date | None:
    """Best-effort as-of date: explicit pattern, a date column, preamble text, then filename."""
    texts = list(preamble) + [context or ""]
    if pattern:
        pat = re.compile(pattern, re.IGNORECASE)
        for t in texts + [filename or ""]:
            m = pat.search(t)
            if m:
                d = parse_date(m.group(1) if m.groups() else m.group(0))
                if d:
                    return d
    if rows:
        d = parse_date(_pick(rows[0], "date", {}))
        if d:
            return d
    for t in texts:
        if re.search(r"as of|holdings|date", t, re.IGNORECASE):
            d = parse_date(t)
            if d:
                return d
    for t in texts:
        d = parse_date(t)
        if d:
            return d
    return parse_date(filename)


def parse_holdings(data: bytes, *, content_type: str | None = None, url: str | None = None,
                   overrides: dict[str, str] | None = None, options: dict | None = None,
                   table_pattern: str | None = None, as_of_pattern: str | None = None,
                   page_text: str | None = None) -> tuple[list[Holding], date | None, dict]:
    """Parse a holdings file. Returns (holdings, as_of_date_or_None, extra_info)."""
    matrix, context = load_matrix(data, content_type, url, table_pattern)
    rows, header, preamble = rows_from_matrix(matrix)
    holdings = normalize_rows(rows, overrides, options)
    if not holdings:
        raise ValueError("holdings file parsed to zero positions")
    if page_text:
        context = (context or "") + " " + page_text
    as_of = detect_as_of(rows, preamble, context, url.rsplit("/", 1)[-1] if url else None, as_of_pattern)
    return holdings, as_of, fund_level_extra(rows, header, overrides)


def fund_level_extra(rows: list[dict], header: list[str], overrides: dict[str, str] | None = None) -> dict:
    """Fund-wide figures some files repeat on every row (net assets, shares outstanding, NAV)."""
    extra: dict = {"header": header, "n_rows": len(rows)}
    if not rows:
        return extra
    overrides = overrides or {}
    for key, syns in (("net_assets", SYNONYMS["net_assets"]),
                      ("shares_outstanding", ["shares outstanding", "sharesoutstanding", "etf shares outstanding"]),
                      ("nav", ["nav", "official nav", "net asset value"])):
        cands = [_norm_header(overrides[key])] if key in overrides else syns
        for syn in cands:
            if syn in rows[0]:
                v = to_float(rows[0][syn])
                if v is not None:
                    extra[key] = v
                break
    return extra
