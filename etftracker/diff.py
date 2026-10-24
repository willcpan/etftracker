"""Compare consecutive snapshots of a fund and classify what the manager did.

The subtlety with ETFs: creations and redemptions change *every* position's share
count proportionally without the manager trading anything. We estimate that flow
factor as the median ratio of shares_now / shares_prev across positions held in
both snapshots, then look for positions whose share count moved by more than the
threshold *after* dividing out that factor. Those are genuine buys/sells.
"""
from __future__ import annotations

import itertools
from statistics import median

from .models import Holding, Snapshot

ACTIONS = ("new", "exit", "add", "trim", "hold")


def _by_key(snap: Snapshot) -> dict[str, Holding]:
    out: dict[str, Holding] = {}
    for h in snap.holdings:
        if h.asset_type != "equity":
            continue
        if h.key in out:  # merge duplicate lines (e.g., multiple lots)
            prev = out[h.key]
            prev.shares = (prev.shares or 0) + (h.shares or 0) if (prev.shares is not None or h.shares is not None) else None
            prev.market_value = (prev.market_value or 0) + (h.market_value or 0) if (prev.market_value is not None or h.market_value is not None) else None
            prev.weight = (prev.weight or 0) + (h.weight or 0) if (prev.weight is not None or h.weight is not None) else None
        else:
            out[h.key] = Holding(**h.__dict__)
    return out


def flow_factor(prev: dict[str, Holding], now: dict[str, Holding]) -> float:
    ratios = []
    for k, h in now.items():
        p = prev.get(k)
        if p and p.shares and h.shares and p.shares > 0 and h.shares > 0:
            ratios.append(h.shares / p.shares)
    if len(ratios) < 3:
        return 1.0
    return float(median(ratios))


def diff_snapshots(prev_snap: Snapshot, now_snap: Snapshot, trade_threshold: float = 0.005,
                   weight_threshold: float = 0.0025) -> dict:
    prev, now = _by_key(prev_snap), _by_key(now_snap)
    factor = flow_factor(prev, now)
    trades: list[dict] = []
    for key in sorted(set(prev) | set(now)):
        p, n = prev.get(key), now.get(key)
        ref = n or p
        rec = {
            "as_of": now_snap.as_of.isoformat(),
            "prev_as_of": prev_snap.as_of.isoformat(),
            "key": key,
            "ticker": ref.ticker,
            "name": ref.name,
            "shares_prev": p.shares if p else None,
            "shares_now": n.shares if n else None,
            "shares_change": None,
            "adj_change": None,
            "weight_prev": p.weight if p else None,
            "weight_now": n.weight if n else None,
            "weight_change": None,
            "est_value": None,
            "flow_factor": factor,
            "basis": "shares",
            "action": "hold",
        }
        if rec["weight_prev"] is not None and rec["weight_now"] is not None:
            rec["weight_change"] = rec["weight_now"] - rec["weight_prev"]
        elif rec["weight_now"] is not None and p is None:
            rec["weight_change"] = rec["weight_now"]
        elif rec["weight_prev"] is not None and n is None:
            rec["weight_change"] = -rec["weight_prev"]

        if p is None:
            rec["action"] = "new"
            if n.shares is not None:
                rec["shares_change"] = n.shares
                rec["adj_change"] = None
                rec["est_value"] = n.market_value if n.market_value is not None else (
                    n.shares * n.price if n.price is not None else None)
        elif n is None:
            rec["action"] = "exit"
            if p.shares is not None:
                rec["shares_change"] = -p.shares
                rec["est_value"] = -(p.market_value if p.market_value is not None else (
                    p.shares * p.price if p.price is not None else 0)) or None
        elif p.shares is not None and n.shares is not None and p.shares > 0:
            expected = p.shares * factor
            rec["shares_change"] = n.shares - p.shares
            rec["adj_change"] = n.shares / expected - 1.0
            active_shares = n.shares - expected
            px = n.price if n.price is not None else (
                (n.market_value / n.shares) if (n.market_value and n.shares) else None)
            rec["est_value"] = active_shares * px if px is not None else None
            if abs(rec["adj_change"]) >= trade_threshold and n.shares != p.shares:
                rec["action"] = "add" if rec["adj_change"] > 0 else "trim"
        else:
            rec["basis"] = "weight"
            wc = rec["weight_change"]
            if wc is not None and abs(wc) >= weight_threshold:
                rec["action"] = "add" if wc > 0 else "trim"
        trades.append(rec)
    return {
        "as_of": now_snap.as_of.isoformat(),
        "prev_as_of": prev_snap.as_of.isoformat(),
        "flow_factor": factor,
        "n_prev": len(prev),
        "n_now": len(now),
        "trades": trades,
    }


def diff_series(snaps: list[Snapshot], trade_threshold: float = 0.005, weight_threshold: float = 0.0025) -> list[dict]:
    """Diff each consecutive pair in a date-sorted list of snapshots."""
    snaps = sorted(snaps, key=lambda s: s.as_of)
    out = []
    for a, b in itertools.pairwise(snaps):
        out.append(diff_snapshots(a, b, trade_threshold, weight_threshold))
    return out
