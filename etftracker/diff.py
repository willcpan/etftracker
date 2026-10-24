"""Compare consecutive snapshots of a fund and classify what the manager did.

The subtlety with ETFs: creations and redemptions change *every* position's share
count proportionally without the manager expressing a view. We first estimate that
**flow factor** (ratio of ETF shares outstanding when the file reports it, otherwise
the median of per-position share ratios), then classify each position by how its
share count moved relative to that factor:

  action      meaning
  ---------   -------------------------------------------------------------------
  new         position did not exist in the previous snapshot
  exit        position is gone
  add         shares grew more than flows explain  (active buy)
  trim        shares fell more than flows explain  (active sell)
  flow        shares moved in step with creations/redemptions (not a signal)
  kept        shares unchanged while the fund had an outflow: selectively preserved
  not_added   shares unchanged while the fund had an inflow: selectively not bought
  hold        shares unchanged on a day with no meaningful flow

`kept` and `not_added` are the quieter signals: on a redemption day most positions
shrink pro rata, so the ones left untouched are the ones the manager chose to keep.
"""
from __future__ import annotations

import itertools
from statistics import median

from .models import Holding, Snapshot

ACTIONS = ("new", "exit", "add", "trim", "flow", "kept", "not_added", "hold")
ACTIVE_ACTIONS = {"new", "exit", "add", "trim", "kept", "not_added"}


def _by_key(snap: Snapshot) -> dict[str, Holding]:
    out: dict[str, Holding] = {}
    for h in snap.holdings:
        if h.asset_type != "equity":
            continue
        if h.key in out:  # merge duplicate lines (e.g., multiple lots)
            prev = out[h.key]
            for attr in ("shares", "market_value", "weight"):
                a, b = getattr(prev, attr), getattr(h, attr)
                if a is not None or b is not None:
                    setattr(prev, attr, (a or 0) + (b or 0))
        else:
            out[h.key] = Holding(**h.__dict__)
    return out


def median_flow_factor(prev: dict[str, Holding], now: dict[str, Holding]) -> float | None:
    ratios = []
    for k, h in now.items():
        p = prev.get(k)
        if p and p.shares and h.shares and p.shares > 0 and h.shares > 0:
            ratios.append(h.shares / p.shares)
    if len(ratios) < 3:
        return None
    return float(median(ratios))


def flow_factor(prev_snap: Snapshot, now_snap: Snapshot, prev: dict[str, Holding], now: dict[str, Holding]) -> tuple[float, str]:
    """Return (factor, basis). basis is 'shares_outstanding', 'median' or 'none'."""
    so0, so1 = prev_snap.extra.get("shares_outstanding"), now_snap.extra.get("shares_outstanding")
    try:
        if so0 and so1 and float(so0) > 0 and float(so1) > 0:
            return float(so1) / float(so0), "shares_outstanding"
    except (TypeError, ValueError):
        pass
    m = median_flow_factor(prev, now)
    if m is not None:
        return m, "median"
    return 1.0, "none"


def diff_snapshots(prev_snap: Snapshot, now_snap: Snapshot, trade_threshold: float = 0.005,
                   weight_threshold: float = 0.0025, min_share_change: float = 0.0,
                   flow_threshold: float = 0.0025) -> dict:
    """Diff two snapshots. ``flow_threshold`` is how large a creation/redemption must be
    (as a fraction of the fund) before the day counts as an inflow/outflow, which is what
    makes an untouched position "kept" or "not added"."""
    prev, now = _by_key(prev_snap), _by_key(now_snap)
    factor, basis = flow_factor(prev_snap, now_snap, prev, now)
    direction = "inflow" if factor - 1 >= flow_threshold else "outflow" if 1 - factor >= flow_threshold else "none"
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
            "flow_direction": direction,
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
                rec["est_value"] = n.market_value if n.market_value is not None else (
                    n.shares * n.price if n.price is not None else None)
        elif n is None:
            rec["action"] = "exit"
            if p.shares is not None:
                rec["shares_change"] = -p.shares
                mv = p.market_value if p.market_value is not None else (p.shares * p.price if p.price is not None else None)
                rec["est_value"] = -mv if mv else None
        elif p.shares is not None and n.shares is not None and p.shares > 0:
            expected = p.shares * factor
            rec["shares_change"] = n.shares - p.shares
            rec["adj_change"] = n.shares / expected - 1.0
            px = n.price if n.price is not None else (
                (n.market_value / n.shares) if (n.market_value and n.shares) else None)
            rec["est_value"] = (n.shares - expected) * px if px is not None else None
            unchanged = abs(n.shares - p.shares) <= min_share_change
            if unchanged:
                # Only call it selective when a pro-rata move would have been visible above
                # the file's rounding noise; otherwise we cannot tell.
                visible = abs(expected - p.shares) > min_share_change
                rec["action"] = {"inflow": "not_added", "outflow": "kept", "none": "hold"}[direction] if visible else "hold"
                if rec["action"] == "hold":
                    rec["est_value"] = None
            elif abs(rec["adj_change"]) >= trade_threshold and abs(n.shares - p.shares) > min_share_change:
                rec["action"] = "add" if rec["adj_change"] > 0 else "trim"
            else:
                rec["action"] = "flow" if direction != "none" or abs(factor - 1) > 1e-9 else "hold"
                rec["est_value"] = None
        else:
            rec["basis"] = "weight"
            wc = rec["weight_change"]
            if wc is not None and abs(wc) >= weight_threshold:
                rec["action"] = "add" if wc > 0 else "trim"
        trades.append(rec)

    prev_assets = prev_snap.extra.get("net_assets") or prev_snap.total_market_value()
    counts = {a: sum(1 for t in trades if t["action"] == a) for a in ACTIONS}
    return {
        "as_of": now_snap.as_of.isoformat(),
        "prev_as_of": prev_snap.as_of.isoformat(),
        "flow_factor": factor,
        "flow_basis": basis,
        "flow_direction": direction,
        "flow_pct": factor - 1.0,
        "flow_value": (factor - 1.0) * float(prev_assets) if prev_assets else None,
        "n_prev": len(prev),
        "n_now": len(now),
        "counts": counts,
        "trades": trades,
    }


def diff_series(snaps: list[Snapshot], trade_threshold: float = 0.005, weight_threshold: float = 0.0025,
                min_share_change: float = 0.0, flow_threshold: float = 0.0025) -> list[dict]:
    """Diff each consecutive pair in a date-sorted list of snapshots."""
    snaps = sorted(snaps, key=lambda s: s.as_of)
    return [diff_snapshots(a, b, trade_threshold, weight_threshold, min_share_change, flow_threshold)
            for a, b in itertools.pairwise(snaps)]
