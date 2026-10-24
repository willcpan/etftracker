from datetime import date

from etftracker.diff import diff_snapshots
from etftracker.models import Holding, Snapshot


def snap(d, rows):
    return Snapshot("X", d, [Holding(t, n, shares=s, price=p, market_value=s * p, weight=w) for t, n, s, p, w in rows])


def test_flow_adjusted_trades():
    # Day 2: fund had 10% creations (all positions x1.10), plus manager added 20% to AAA,
    # trimmed BBB by 30%, exited CCC, started DDD. EEE untouched.
    prev = snap(date(2026, 1, 2), [
        ("AAA", "A", 1000, 10, 0.25), ("BBB", "B", 1000, 10, 0.25), ("CCC", "C", 1000, 10, 0.25),
        ("EEE", "E", 1000, 10, 0.25), ("FFF", "F", 2000, 5, 0.25),
    ])
    now = snap(date(2026, 1, 3), [
        ("AAA", "A", 1320, 10, 0.3), ("BBB", "B", 770, 10, 0.175), ("DDD", "D", 500, 20, 0.2),
        ("EEE", "E", 1100, 10, 0.25), ("FFF", "F", 2200, 5, 0.25),
    ])
    d = diff_snapshots(prev, now, trade_threshold=0.005)
    assert abs(d["flow_factor"] - 1.1) < 1e-9
    by = {t["key"]: t for t in d["trades"]}
    assert by["T:AAA"]["action"] == "add" and abs(by["T:AAA"]["adj_change"] - 0.2) < 1e-9
    assert abs(by["T:AAA"]["est_value"] - (1320 - 1100) * 10) < 1e-6
    assert by["T:BBB"]["action"] == "trim" and abs(by["T:BBB"]["adj_change"] + 0.3) < 1e-9
    assert by["T:CCC"]["action"] == "exit" and by["T:CCC"]["est_value"] == -10000
    assert by["T:DDD"]["action"] == "new" and by["T:DDD"]["est_value"] == 10000
    assert by["T:EEE"]["action"] == "hold"
    assert by["T:FFF"]["action"] == "hold"


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
    assert d["flow_factor"] == 1.0
    assert [t["key"] for t in d["trades"]] == ["T:AAA"]
    assert d["trades"][0]["action"] == "add"
