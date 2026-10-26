"""Compute analytics across all stored snapshots and write static JSON for the web app.

Output layout (``site_data_dir``):
  index.json            funds overview + recent activity feed
  activity.json         every detected trade, newest first
  securities.json       cross-holdings: which funds own what
  funds/<TICKER>.json   full detail for one fund: latest holdings, history matrix, trades
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .config import Config
from .diff import ACTIVE_ACTIONS, diff_series
from .store import Store
from .util import now_utc_iso

COUNTED_ACTIONS = ("new", "exit", "add", "trim", "kept", "not_added", "flow")


def _r(x, nd=6):
    return None if x is None else round(x, nd)


def _holding_json(h, prev=None) -> dict:
    d = {
        "key": h.key,
        "ticker": h.ticker,
        "name": h.name,
        "cusip": h.cusip,
        "asset_type": h.asset_type,
        "shares": _r(h.shares, 4),
        "price": _r(h.price, 4),
        "market_value": _r(h.market_value, 2),
        "weight": _r(h.weight, 6),
    }
    return d


def fund_analytics(store: Store, config: Config, ticker: str) -> dict | None:
    snaps = store.read_all(ticker)
    if not snaps:
        return None
    try:
        fund = config.fund(ticker)
        meta = {"ticker": fund.ticker, "name": fund.name, "manager": fund.manager, "website": fund.website,
                "exchange": fund.exchange, "inception": fund.inception}
        opts = fund.options
    except KeyError:
        meta = {"ticker": ticker, "name": ticker, "manager": "", "website": None, "exchange": None, "inception": None}
        opts = {}
    tt = float(opts.get("trade_threshold", config.settings.trade_threshold))
    wt = float(opts.get("weight_threshold", config.settings.weight_threshold))
    min_share_change = float(opts.get("min_share_change", 0))
    ft = float(opts.get("flow_threshold", config.settings.flow_threshold))
    diffs = diff_series(snaps, tt, wt, min_share_change, ft)
    latest = snaps[-1]
    prev = snaps[-2] if len(snaps) > 1 else None
    latest_diff = diffs[-1] if diffs else None
    latest_trades = {t["key"]: t for t in latest_diff["trades"]} if latest_diff else {}

    # ---- latest holdings table ---------------------------------------------------
    holdings = []
    for h in sorted(latest.holdings, key=lambda x: -(x.weight or 0)):
        d = _holding_json(h)
        t = latest_trades.get(h.key)
        if t:
            d["change"] = {k: _r(t[k], 6) for k in ("shares_change", "adj_change", "weight_change", "est_value")}
            d["change"]["action"] = t["action"]
            d["change"]["weight_prev"] = _r(t["weight_prev"], 6)
            d["change"]["flow_direction"] = t["flow_direction"]
        holdings.append(d)

    # ---- history matrix (equities only) -----------------------------------------
    dates = [s.as_of.isoformat() for s in snaps]
    keys: dict[str, dict] = {}
    for s in snaps:
        for h in s.holdings:
            if h.asset_type != "equity":
                continue
            keys.setdefault(h.key, {"key": h.key, "ticker": h.ticker, "name": h.name})
            keys[h.key]["name"] = h.name  # latest name wins
    key_list = list(keys)
    idx = {k: i for i, k in enumerate(key_list)}
    weights = [[None] * len(dates) for _ in key_list]
    shares = [[None] * len(dates) for _ in key_list]
    for j, s in enumerate(snaps):
        for h in s.holdings:
            if h.key in idx:
                i = idx[h.key]
                weights[i][j] = _r(((weights[i][j] or 0) + h.weight) if h.weight is not None else weights[i][j], 6)
                shares[i][j] = _r(((shares[i][j] or 0) + h.shares) if h.shares is not None else shares[i][j], 4)
    # order securities by latest weight desc
    order = sorted(range(len(key_list)), key=lambda i: -(weights[i][-1] or 0))
    history = {
        "dates": dates,
        "securities": [keys[key_list[i]] for i in order],
        "weights": [weights[i] for i in order],
        "shares": [shares[i] for i in order],
        "cash_weight": [_r(sum((h.weight or 0) for h in s.holdings if h.asset_type == "cash"), 6) for s in snaps],
        "n_positions": [len(s.equities) for s in snaps],
        "net_assets": [s.extra.get("net_assets") or _r(s.total_market_value(), 2) for s in snaps],
        "shares_outstanding": [s.extra.get("shares_outstanding") for s in snaps],
    }

    # ---- trade log ------------------------------------------------------------------
    trade_log = []
    for d in diffs:
        for t in d["trades"]:
            if t["action"] in ACTIVE_ACTIONS:
                trade_log.append({**{k: _r(v, 6) if isinstance(v, float) else v for k, v in t.items()}, "fund": ticker})
    trade_log.sort(key=lambda t: (t["as_of"], -(abs(t["est_value"] or 0))), reverse=True)

    # ---- flow events: one per snapshot pair, describing creations/redemptions ------
    flows = []
    for d in diffs:
        by_action = {a: [t["ticker"] or t["name"] for t in d["trades"] if t["action"] == a]
                     for a in ("kept", "not_added", "add", "trim", "new", "exit")}
        flows.append({
            "fund": ticker,
            "as_of": d["as_of"],
            "prev_as_of": d["prev_as_of"],
            "flow_factor": _r(d["flow_factor"], 6),
            "flow_basis": d["flow_basis"],
            "flow_direction": d["flow_direction"],
            "flow_handling": d["flow_handling"],
            "n_unchanged": d["n_unchanged"],
            "n_scaled": d["n_scaled"],
            "flow_pct": _r(d["flow_pct"], 6),
            "flow_value": _r(d["flow_value"], 2),
            "counts": {a: d["counts"][a] for a in COUNTED_ACTIONS},
            "n_positions": d["n_now"],
            "tickers": by_action,
        })

    summary_changes = {a: 0 for a in COUNTED_ACTIONS}
    if latest_diff:
        for a in COUNTED_ACTIONS:
            summary_changes[a] = latest_diff["counts"][a]

    cash_w = sum((h.weight or 0) for h in latest.holdings if h.asset_type == "cash")
    return {
        "fund": meta,
        "generated_at": now_utc_iso(),
        "latest_as_of": latest.as_of.isoformat(),
        "prev_as_of": prev.as_of.isoformat() if prev else None,
        "fetched_at": latest.fetched_at,
        "source_url": latest.source_url,
        "n_snapshots": len(snaps),
        "n_positions": len(latest.equities),
        "net_assets": latest.extra.get("net_assets") or _r(latest.total_market_value(), 2),
        "cash_weight": _r(cash_w, 6),
        "flow_factor": _r(latest_diff["flow_factor"], 6) if latest_diff else None,
        "latest_flow": flows[-1] if flows else None,
        "latest_changes": summary_changes,
        "trade_threshold": tt,
        "flow_threshold": ft,
        "holdings": holdings,
        "history": history,
        "trades": trade_log,
        "flows": flows,
        "_trades_all": [t for d in diffs for t in d["trades"]],  # stripped before writing; used for sqlite
    }


def export_site(store: Store, config: Config, out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    (out_dir / "funds").mkdir(parents=True, exist_ok=True)
    funds_out = []
    activity: list[dict] = []
    all_flows: list[dict] = []
    securities: dict[str, dict] = {}
    trades_by_fund: dict[str, list[dict]] = {}
    tickers = [f.ticker for f in config.funds if f.enabled]
    for t in store.funds():
        if t not in tickers:
            tickers.append(t)
    for ticker in tickers:
        fa = fund_analytics(store, config, ticker)
        if fa is None:
            continue
        trades_by_fund[ticker] = fa.pop("_trades_all")
        (out_dir / "funds" / f"{ticker}.json").write_text(json.dumps(fa, separators=(",", ":")))
        activity.extend(fa["trades"])
        all_flows.extend(fa["flows"])
        top = [{"ticker": h["ticker"], "name": h["name"], "weight": h["weight"]}
               for h in fa["holdings"] if h["asset_type"] == "equity"][:10]
        funds_out.append({
            **fa["fund"],
            "latest_as_of": fa["latest_as_of"],
            "prev_as_of": fa["prev_as_of"],
            "n_snapshots": fa["n_snapshots"],
            "n_positions": fa["n_positions"],
            "net_assets": fa["net_assets"],
            "cash_weight": fa["cash_weight"],
            "latest_changes": fa["latest_changes"],
            "latest_flow": fa["latest_flow"],
            "top_holdings": top,
            "first_as_of": fa["history"]["dates"][0],
        })
        for h in fa["holdings"]:
            if h["asset_type"] != "equity" or not h["weight"]:
                continue
            sec = securities.setdefault(h["key"], {"key": h["key"], "ticker": h["ticker"], "name": h["name"], "funds": []})
            sec["funds"].append({"fund": ticker, "weight": h["weight"], "shares": h["shares"],
                                 "market_value": h["market_value"], "as_of": fa["latest_as_of"],
                                 "action": (h.get("change") or {}).get("action")})
    activity.sort(key=lambda t: (t["as_of"], abs(t["est_value"] or 0)), reverse=True)
    cutoff = (date.today() - timedelta(days=45)).isoformat()
    recent = [t for t in activity if t["as_of"] >= cutoff][:100]
    all_flows.sort(key=lambda f: f["as_of"], reverse=True)
    index = {
        "generated_at": now_utc_iso(),
        "funds": funds_out,
        "recent_activity": recent,
        "recent_flows": [f for f in all_flows if f["as_of"] >= cutoff][:100],
        "n_securities": len(securities),
    }
    (out_dir / "index.json").write_text(json.dumps(index, separators=(",", ":")))
    (out_dir / "activity.json").write_text(json.dumps({"trades": activity[:5000], "flows": all_flows[:3000]},
                                                      separators=(",", ":")))
    sec_list = sorted(securities.values(), key=lambda s: (-len(s["funds"]), -sum(f["weight"] for f in s["funds"])))
    (out_dir / "securities.json").write_text(json.dumps({"securities": sec_list}, separators=(",", ":")))
    return {"funds": [f["ticker"] for f in funds_out], "trades": len(activity), "trades_by_fund": trades_by_fund}
