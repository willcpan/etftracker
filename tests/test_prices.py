from datetime import date
from pathlib import Path

from etftracker.prices import Bar, PriceStore, estimate_fill, yahoo_symbol


def test_symbol_mapping():
    assert yahoo_symbol("AMZN") == "AMZN"
    assert yahoo_symbol("AMZN US") == "AMZN"
    assert yahoo_symbol("BRK/B") == "BRK-B"
    assert yahoo_symbol("CSU CN") == "CSU.TO"
    assert yahoo_symbol("RR/ LN") == "RR.L"
    assert yahoo_symbol("UMG NA") == "UMG.AS"
    assert yahoo_symbol("MC FP") == "MC.PA"
    assert yahoo_symbol("SAP GR") == "SAP.DE"
    assert yahoo_symbol("2299955D CN") is None  # unlisted warrant placeholder
    assert yahoo_symbol("XYZ ZZ") is None  # unknown exchange code
    assert yahoo_symbol(None) is None
    assert yahoo_symbol("CSU CN", {"CSU CN": "CSU.TO"}) == "CSU.TO"
    assert yahoo_symbol("FOO", {"FOO": ""}) is None


def bars(*rows):
    return {date.fromisoformat(d): Bar(date.fromisoformat(d), o, h, lo, c, v) for d, o, h, lo, c, v in rows}


def test_estimate_fill_single_day_typical_price():
    b = bars(("2026-10-26", 100, 110, 90, 100, 1000), ("2026-10-27", 100, 104, 98, 102, 2000))
    est = estimate_fill(b, date(2026, 10, 26), date(2026, 10, 27), fund_close_usd=102.0)
    assert est["px_days"] == 1
    assert abs(est["px_est"] - (104 + 98 + 102) / 3) < 1e-3
    assert est["px_low"] == 98 and est["px_high"] == 104 and est["px_scale"] == 1.0


def test_estimate_fill_multi_day_volume_weighted_and_fx_scaled():
    # Local-currency bars (e.g. CAD) while the fund reports USD: scale by fund close / local close.
    b = bars(("2026-10-27", 10, 12, 8, 10, 100), ("2026-10-28", 10, 22, 18, 20, 300))
    est = estimate_fill(b, date(2026, 10, 26), date(2026, 10, 28), fund_close_usd=15.0)  # local close 20 -> 0.75
    typical = ((12 + 8 + 10) / 3 * 100 + (22 + 18 + 20) / 3 * 300) / 400
    assert est["px_days"] == 2
    assert abs(est["px_scale"] - 0.75) < 1e-9
    assert abs(est["px_est"] - typical * 0.75) < 1e-3
    assert abs(est["px_low"] - 8 * 0.75) < 1e-9 and abs(est["px_high"] - 22 * 0.75) < 1e-9


def test_estimate_fill_no_bars_in_window():
    b = bars(("2026-10-20", 1, 1, 1, 1, 1))
    assert estimate_fill(b, date(2026, 10, 26), date(2026, 10, 27), None) is None


def test_price_store_roundtrip(tmp_path: Path):
    store = PriceStore(tmp_path)
    b = bars(("2026-10-27", 1.5, 2, 1, 1.75, None), ("2026-10-28", 2, 3, 1.5, 2.5, 12345))
    store.write("BRK-B", b)
    back = store.read("BRK-B")
    assert back[date(2026, 10, 27)].volume is None
    assert back[date(2026, 10, 28)] == b[date(2026, 10, 28)]
    assert store.read("NOPE") == {}
