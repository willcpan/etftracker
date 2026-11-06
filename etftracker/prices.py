"""Daily market prices for estimating the price at which detected trades were filled.

Holdings files give each position's end-of-day price in the fund's base currency, but a
trade that shows up between two snapshots was executed during the trading day(s) in
between. We fetch daily open/high/low/close/volume bars for those tickers, cache them
in ``data/prices/<SYMBOL>.csv`` (committed with the snapshots), and estimate the fill as
the volume-weighted *typical price* ((high + low + close) / 3, a standard VWAP proxy)
across the days in the window, with the window's low..high as the plausible range.

Foreign lines are quoted in local currency by market-data providers while the fund
reports USD, so bars are scaled by (fund close in USD) / (provider close) before use.

Providers, in order:
  * Tiingo (https://www.tiingo.com), when ``TIINGO_API_KEY`` is set: reliable, documented,
    free tier covers U.S.-listed stocks and ADRs, which is most of what these funds hold.
  * Yahoo Finance's public chart endpoint, no key: covers foreign listings too, but it is
    unofficial and rate-limits automated clients aggressively, so it is best-effort only.
When no provider has a symbol the trade keeps the fund file's close.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import ClassVar

import httpx

log = logging.getLogger("etftracker.prices")

# Bloomberg-style exchange codes -> Yahoo Finance suffixes
YAHOO_SUFFIX = {
    "US": "", "UW": "", "UN": "", "UQ": "", "UA": "", "UR": "",
    "CN": ".TO", "CT": ".TO", "CV": ".V",
    "LN": ".L", "NA": ".AS", "FP": ".PA", "GR": ".DE", "GY": ".DE", "SW": ".SW", "SE": ".SW", "IM": ".MI",
    "SM": ".MC", "SS": ".ST", "DC": ".CO", "NO": ".OL", "FH": ".HE", "BB": ".BR", "PL": ".LS", "ID": ".IR",
    "JP": ".T", "JT": ".T", "HK": ".HK", "AU": ".AX", "SP": ".SI", "KS": ".KS", "TT": ".TW", "IN": ".NS",
}


@dataclass(frozen=True)
class Bar:
    date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None


def yahoo_symbol(ticker: str | None, overrides: dict[str, str] | None = None) -> str | None:
    """Map a holdings-file ticker ('BRK/B', 'CSU CN', 'RR/ LN') to a Yahoo symbol, or None."""
    if not ticker:
        return None
    t = " ".join(ticker.upper().split())
    if overrides and t in overrides:
        return overrides[t] or None
    if re.search(r"\d{5,}[A-Z]?\b", t.split()[0]):  # placeholder ids like '2299955D' (warrants, unlisted)
        return None
    parts = t.split()
    base, exch = (parts[0], parts[1]) if len(parts) == 2 else (parts[0], "US")
    if len(parts) > 2 or exch not in YAHOO_SUFFIX:
        return None
    base = base.rstrip("/")  # 'RR/' (LSE style) -> 'RR'
    base = base.replace("/", "-").replace(".", "-")  # 'BRK/B' -> 'BRK-B'
    return base + YAHOO_SUFFIX[exch]




# ---- providers ---------------------------------------------------------------------
UA = "etftracker/0.1 (+https://github.com/willcpan/etftracker)"


def fetch_yahoo(symbol: str, start: date, end: date, client: httpx.Client) -> list[Bar]:
    p1 = int(datetime(start.year, start.month, start.day, tzinfo=UTC).timestamp())
    p2 = int(datetime(end.year, end.month, end.day, tzinfo=UTC).timestamp()) + 86400
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    r = client.get(url, params={"period1": p1, "period2": p2, "interval": "1d", "events": "div,splits"},
                   headers={"User-Agent": UA, "Accept": "application/json"})
    r.raise_for_status()
    res = r.json().get("chart", {}).get("result") or []
    if not res:
        return []
    res = res[0]
    ts = res.get("timestamp") or []
    q = (res.get("indicators", {}).get("quote") or [{}])[0]
    bars = []
    for i, t in enumerate(ts):
        d = datetime.fromtimestamp(t, tz=UTC).date()
        c = q.get("close", [None])[i]
        if c is None:
            continue
        bars.append(Bar(d, q.get("open", [None])[i], q.get("high", [None])[i], q.get("low", [None])[i], c,
                        q.get("volume", [None])[i]))
    return bars


def tiingo_key() -> str | None:
    return os.environ.get("TIINGO_API_KEY") or None


def fetch_tiingo(symbol: str, start: date, end: date, client: httpx.Client) -> list[Bar]:
    """Tiingo end-of-day prices. Symbols use '-' for share classes (BRK-B); foreign
    exchange suffixes (.TO, .L, ...) are not covered on the free tier and are skipped."""
    if "." in symbol:
        return []
    key = tiingo_key()
    if not key:
        return []
    url = f"https://api.tiingo.com/tiingo/daily/{symbol}/prices"
    r = client.get(url, params={"startDate": start.isoformat(), "endDate": end.isoformat(), "resampleFreq": "daily"},
                   headers={"User-Agent": UA, "Accept": "application/json", "Authorization": f"Token {key}"})
    if r.status_code == 404:
        return []
    r.raise_for_status()
    bars = []
    for row in r.json():
        try:
            d = date.fromisoformat(str(row["date"])[:10])
            bars.append(Bar(d, row.get("open"), row.get("high"), row.get("low"), row.get("close"), row.get("volume")))
        except (KeyError, ValueError, TypeError):
            continue
    return bars


_last_request = 0.0
MIN_INTERVAL = 1.5  # seconds between provider requests; Yahoo rate-limits bursts hard


def _throttle() -> None:
    global _last_request
    wait = MIN_INTERVAL - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def _with_backoff(fn, label: str, attempts: int = 4) -> list[Bar]:
    delay = 5.0
    for i in range(attempts):
        _throttle()
        try:
            return fn()
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (429, 503) and i < attempts - 1:
                log.info("%s: rate limited, retrying in %.0fs", label, delay)
                time.sleep(delay)
                delay *= 3
                continue
            log.warning("%s failed: %s", label, e)
            return []
        except (httpx.HTTPError, ValueError) as e:
            log.warning("%s failed: %s", label, e)
            return []
    return []


# ---- cache ---------------------------------------------------------------------------
class PriceStore:
    COLUMNS: ClassVar[list[str]] = ["date", "open", "high", "low", "close", "volume"]

    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir) / "prices"

    def _path(self, symbol: str) -> Path:
        return self.dir / f"{symbol.replace('/', '_')}.csv"

    def read(self, symbol: str) -> dict[date, Bar]:
        p = self._path(symbol)
        out: dict[date, Bar] = {}
        if not p.exists():
            return out
        with p.open(newline="") as f:
            for row in csv.DictReader(f):
                vals = [float(row[k]) if row.get(k) not in (None, "") else None for k in self.COLUMNS[1:]]
                d = date.fromisoformat(row["date"])
                out[d] = Bar(d, *vals)
        return out

    def write(self, symbol: str, bars: dict[date, Bar]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        with self._path(symbol).open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(self.COLUMNS)
            for d in sorted(bars):
                b = bars[d]
                w.writerow([d.isoformat()] + [("" if v is None else f"{v:.6g}") for v in (b.open, b.high, b.low, b.close, b.volume)])

    def meta_path(self) -> Path:
        return self.dir / "_symbols.json"

    def read_meta(self) -> dict:
        p = self.meta_path()
        return json.loads(p.read_text()) if p.exists() else {}

    def write_meta(self, meta: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.meta_path().write_text(json.dumps(meta, indent=1, sort_keys=True) + "\n")


def ensure_bars(store: PriceStore, symbol: str, start: date, end: date, client: httpx.Client,
                meta: dict) -> dict[date, Bar]:
    """Return cached bars for [start, end], fetching the missing span from a provider."""
    bars = store.read(symbol)
    have = [d for d in bars if start <= d <= end]
    # Treat the range as covered if we have a bar for the last business day on or before `end`
    # and for the first on or after `start`.
    need_from = start
    if have:
        latest = max(have)
        if latest >= end - timedelta(days=3) and min(have) <= start + timedelta(days=3):
            return bars
        need_from = min(start, latest)
    fetched: list[Bar] = []
    source = None
    providers = [("tiingo", fetch_tiingo)] if tiingo_key() else []
    providers.append(("yahoo", fetch_yahoo))
    for name, fn in providers:
        fetched = _with_backoff(lambda fn=fn: fn(symbol, need_from - timedelta(days=7), end, client), f"{symbol} via {name}")
        if fetched:
            source = name
            break
    if not fetched:
        meta.setdefault("failed", {})[symbol] = datetime.now(UTC).date().isoformat()
        return bars
    for b in fetched:
        bars[b.date] = b
    store.write(symbol, bars)
    meta.setdefault("sources", {})[symbol] = source
    meta.setdefault("failed", {}).pop(symbol, None)
    return bars


# ---- estimation ---------------------------------------------------------------------
def estimate_fill(bars: dict[date, Bar], after: date, through: date, fund_close_usd: float | None) -> dict | None:
    """Estimate the fill price for a trade executed in (after, through].

    Returns {px_est, px_low, px_high, px_days, px_scale} in the fund's currency, or None."""
    days = sorted(d for d in bars if after < d <= through)
    if not days:
        return None
    last = bars[days[-1]]
    scale = 1.0
    if fund_close_usd and last.close:
        ratio = fund_close_usd / last.close
        # Only treat it as an FX/ADR conversion when the ratio is clearly not ~1.
        if abs(ratio - 1) > 0.02:
            scale = ratio
    num = den = 0.0
    lows, highs = [], []
    for d in days:
        b = bars[d]
        if b.high is None or b.low is None or b.close is None:
            continue
        typical = (b.high + b.low + b.close) / 3
        w = b.volume or 1.0
        num += typical * w
        den += w
        lows.append(b.low)
        highs.append(b.high)
    if not den:
        return None
    return {
        "px_est": round(num / den * scale, 4),
        "px_low": round(min(lows) * scale, 4),
        "px_high": round(max(highs) * scale, 4),
        "px_days": len(lows),
        "px_scale": round(scale, 6),
    }
