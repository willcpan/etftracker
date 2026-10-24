from datetime import date

from etftracker.diff import diff_snapshots
from etftracker.models import Holding, Snapshot


def snap(d, rows, **extra):
    return Snapshot("X", d, [Holding(t, n, shares=s, price=p, market_value=s * p, weight=w) for t, n, s, p, w in rows],
                    extra=extra)


def test_flow_adjusted_trades_with_median_factor():
    # Day 2: 10% creations (all positions x1.10), plus manager added 20% to AAA,
    # trimmed BBB by 30%, exited CCC, started DDD. EEE/FFF/GGG scaled with flows only.
    prev = snap(date(2026, 1, 2), [
        ("AAA", "A", 1000, 10, 0.2), ("BBB", "B", 1000, 10, 0.2), ("CCC", "C", 1000, 10, 0.2),
        ("EEE", "E", 1000, 10, 0.2), ("FFF", "F", 2000, 5, 0.1), ("GGG", "G", 3000, 5, 0.1),
    ])
    now = snap(date(2026, 1, 3), [
        ("AAA", "A", 1320, 10, 0.3), ("BBB", "B", 770, 10, 0.175), ("DDD", "D", 500, 20, 0.2),
        ("EEE", "E", 1100, 10, 0.25), ("FFF", "F", 2200, 5, 0.25), ("GGG", "G", 3300, 5, 0.1),
    ])
    d = diff_snapshots(prev, now, trade_threshold=0.005)
    assert abs(d["flow_factor"] - 1.1) < 1e-9 and d["flow_basis"] == "median" and d["flow_direction"] == "inflow"
    by = {t["key"]: t for t in d["trades"]}
    assert by["T:AAA"]["action"] == "add" and abs(by["T:AAA"]["adj_change"] - 0.2) < 1e-9
    assert abs(by["T:AAA"]["est_value"] - (1320 - 1100) * 10) < 1e-6
    assert by["T:BBB"]["action"] == "trim" and abs(by["T:BBB"]["adj_change"] + 0.3) < 1e-9
    assert by["T:CCC"]["action"] == "exit" and by["T:CCC"]["est_value"] == -10000
    assert by["T:DDD"]["action"] == "new" and by["T:DDD"]["est_value"] == 10000
    assert by["T:EEE"]["action"] == "flow" and by["T:EEE"]["est_value"] is None
    assert by["T:FFF"]["action"] == "flow"
    assert d["counts"]["flow"] == 3 and d["counts"]["add"] == 1
    assert abs(d["flow_value"] - 0.1 * 65000) < 1e-6  # 10% of prior market value


def test_shares_outstanding_beats_median_and_flags_selective_cuts():
    # Redemption of 5% (from shares outstanding). Three positions cut exactly pro rata,
    # AAA untouched (kept), BBB cut 20% (selective trim), CCC *bought* against the outflow.
    prev = snap(date(2026, 1, 2), [
        ("AAA", "A", 1000, 10, 0.2), ("BBB", "B", 1000, 10, 0.2), ("CCC", "C", 1000, 10, 0.2),
        ("DDD", "D", 1000, 10, 0.2), ("EEE", "E", 1000, 10, 0.1), ("FFF", "F", 1000, 10, 0.1),
    ], shares_outstanding=100_000)
    now = snap(date(2026, 1, 3), [
        ("AAA", "A", 1000, 10, 0.21), ("BBB", "B", 800, 10, 0.17), ("CCC", "C", 1100, 10, 0.23),
        ("DDD", "D", 950, 10, 0.2), ("EEE", "E", 950, 10, 0.1), ("FFF", "F", 950, 10, 0.1),
    ], shares_outstanding=95_000)
    d = diff_snapshots(prev, now, trade_threshold=0.005)
    assert abs(d["flow_factor"] - 0.95) < 1e-9 and d["flow_basis"] == "shares_outstanding"
    assert d["flow_direction"] == "outflow"
    by = {t["key"]: t for t in d["trades"]}
    assert by["T:AAA"]["action"] == "kept"
    assert abs(by["T:AAA"]["est_value"] - 50 * 10) < 1e-6  # 50 shares not sold = $500 relative buy
    assert by["T:BBB"]["action"] == "trim"
    assert by["T:CCC"]["action"] == "add" and by["T:CCC"]["flow_direction"] == "outflow"
    assert {by[k]["action"] for k in ("T:DDD", "T:EEE", "T:FFF")} == {"flow"}
    assert d["counts"] == {"new": 0, "exit": 0, "add": 1, "trim": 1, "flow": 3, "kept": 1, "not_added": 0, "hold": 0}


def test_not_added_on_inflow_and_hold_when_no_flow():
    prev = snap(date(2026, 1, 2), [("AAA", "A", 1000, 10, 0.5), ("BBB", "B", 1000, 10, 0.3),
                                   ("CCC", "C", 1000, 10, 0.2)], shares_outstanding=100)
    now = snap(date(2026, 1, 3), [("AAA", "A", 1000, 10, 0.48), ("BBB", "B", 1030, 10, 0.3),
                                  ("CCC", "C", 1030, 10, 0.22)], shares_outstanding=103)
    by = {t["key"]: t for t in diff_snapshots(prev, now)["trades"]}
    assert by["T:AAA"]["action"] == "not_added" and by["T:BBB"]["action"] == "flow"
    quiet = diff_snapshots(prev, prev)
    assert quiet["flow_direction"] == "none"
    assert {t["action"] for t in quiet["trades"]} == {"hold"}


def test_min_share_change_treats_rounding_noise_as_unchanged():
    prev = snap(date(2026, 1, 2), [("AAA", "A", 100, 10, 0.5), ("BBB", "B", 100, 10, 0.3), ("CCC", "C", 100, 10, 0.2)],
                shares_outstanding=1000)
    now = snap(date(2026, 1, 3), [("AAA", "A", 101, 10, 0.5), ("BBB", "B", 100, 10, 0.3), ("CCC", "C", 100, 10, 0.2)],
               shares_outstanding=1000)
    by = {t["key"]: t for t in diff_snapshots(prev, now, min_share_change=2)["trades"]}
    assert by["T:AAA"]["action"] == "hold"


def test_weight_basis_when_no_shares():
    prev = Snapshot("X", date(2026, 1, 2), [Holding("AAA", "A", weight=0.10), Holding("BBB", "B", weight=0.10)])
    now = Snapshot("X", date(2026, 1, 3), [Holding("AAA", "A", weight=0.13), Holding("BBB", "B", weight=0.101)])
    d = diff_snapshots(prev, now, weight_threshold=0.0025)
    by = {t["key"]: t for t in d["trades"]}
    assert by["T:AAA"]["action"] == "add" and by["T:AAA"]["basis"] == "weight"
    assert by["T:BBB"]["action"] == "hold"


def test_cash_rows_ignored_and_few_positions_no_flow():
    prev = Snapshot("X", date(2026, 1, 2), [Holding("AAA", "A", shares=100), Holding("CASH", "Cash", asset_type="cash", shares=5)])
    now = Snapshot("X", date(2026, 1, 3), [Holding("AAA", "A", shares=120), Holding("CASH", "Cash", asset_type="cash", shares=50)])
    d = diff_snapshots(prev, now)
    assert d["flow_factor"] == 1.0 and d["flow_basis"] == "none"
    assert [t["key"] for t in d["trades"]] == ["T:AAA"]
    assert d["trades"][0]["action"] == "add"
