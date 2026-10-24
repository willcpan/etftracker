"""fetch -> parse -> dedupe -> persist, one fund at a time."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from .config import Config, Fund
from .models import Snapshot
from .parse import detect_as_of, fund_level_extra, load_matrix, normalize_rows, rows_from_matrix
from .sources import FetchError, fetch_fund
from .store import Store, sha256
from .util import now_utc_iso, parse_date, previous_business_day, today_et

log = logging.getLogger("etftracker")


@dataclass
class CaptureResult:
    fund: str
    status: str  # "new" | "unchanged" | "restated" | "error"
    as_of: date | None = None
    n_holdings: int = 0
    message: str = ""


def parse_fetched(fund: Fund, fetched) -> tuple[list, date | None, dict]:
    src_opts = fund.options
    if fetched.rows is not None:
        header = list(fetched.rows[0].keys())
        matrix = [header] + [["" if r.get(h) is None else str(r.get(h)) for h in header] for r in fetched.rows]
        rows, header_n, preamble = rows_from_matrix(matrix)
        context = ""
    else:
        matrix, context = load_matrix(fetched.data, fetched.content_type, fetched.url, fund.source.table_pattern)
        rows, header_n, preamble = rows_from_matrix(matrix)
    holdings = normalize_rows(rows, fund.columns, src_opts)
    if not holdings:
        raise ValueError("parsed zero positions")
    as_of = parse_date(fetched.as_of_hint) if fetched.as_of_hint else None
    if as_of is None:
        filename = fetched.url.rsplit("/", 1)[-1] if fetched.url else None
        as_of = detect_as_of(rows, preamble, (context or "") + " " + (fetched.page_text or ""), filename,
                             fund.source.as_of_pattern)
    cash_col = src_opts.get("cash_value_column")
    if cash_col and rows:
        # Some basket files carry the fund's cash balance as a fund-level field on every row.
        from .models import Holding
        from .parse import _norm_header
        from .util import to_float

        cash_value = to_float(rows[0].get(_norm_header(cash_col)))
        if cash_value is not None:
            holdings = [h for h in holdings if not (h.asset_type == "cash" and not h.market_value and not h.weight)]
            na = to_float(rows[0].get(_norm_header(fund.columns.get("net_assets", "net assets"))))
            holdings.append(Holding(ticker="CASH", name="Cash & equivalents", asset_type="cash", shares=cash_value,
                                    price=1.0, market_value=cash_value,
                                    weight=(cash_value / na) if na else None))
    if as_of and src_opts.get("as_of_adjust") == "prev_business_day":
        as_of = previous_business_day(as_of)
    extra = fund_level_extra(rows, header_n, fund.columns)
    if fetched.payload and isinstance(fetched.payload, dict):
        for k in ("netAssets", "net_assets", "totalNetAssets"):
            if k in fetched.payload and "net_assets" not in extra:
                extra["net_assets"] = fetched.payload[k]
    return holdings, as_of, extra


def capture(fund: Fund, config: Config, store: Store, *, force: bool = False) -> CaptureResult:
    try:
        fetched, used = fetch_fund(fund, config.settings)
    except FetchError as e:
        log.error("%s: fetch failed: %s", fund.ticker, e)
        return CaptureResult(fund.ticker, "error", message=str(e))
    try:
        holdings, as_of, extra = parse_fetched(fund, fetched)
    except Exception as e:
        log.exception("%s: parse failed", fund.ticker)
        return CaptureResult(fund.ticker, "error", message=f"parse failed: {e}")
    digest = sha256(fetched.data)
    if as_of is None:
        # No date in the file: assume it reflects the previous business day's close.
        as_of = today_et()
        log.warning("%s: no as-of date found; using fetch date %s", fund.ticker, as_of)
    if as_of > today_et():
        log.warning("%s: as-of date %s is in the future; clamping to today", fund.ticker, as_of)
        as_of = today_et()
    existing = store.existing_sha(fund.ticker, as_of)
    if existing == digest and not force:
        return CaptureResult(fund.ticker, "unchanged", as_of, len(holdings), "identical file already stored")
    if existing is None and store.latest_sha(fund.ticker) == digest and not force:
        # Same bytes as the most recent snapshot but under a new date: the publisher
        # hasn't updated yet (holiday, lag). Don't record a duplicate snapshot.
        return CaptureResult(fund.ticker, "unchanged", as_of, len(holdings), "same content as latest snapshot")
    snap = Snapshot(
        fund=fund.ticker,
        as_of=as_of,
        holdings=holdings,
        fetched_at=now_utc_iso(),
        source_url=fetched.url,
        sha256=digest,
        content_type=fetched.content_type,
        extra={k: v for k, v in extra.items() if k != "header"},
    )
    store.write_snapshot(snap, fetched.data)
    status = "restated" if existing else "new"
    log.info("%s: %s snapshot as of %s with %d positions (%s)", fund.ticker, status, as_of, len(holdings), used.type)
    return CaptureResult(fund.ticker, status, as_of, len(holdings))
