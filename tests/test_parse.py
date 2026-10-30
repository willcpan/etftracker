from pathlib import Path

import pytest

from etftracker.config import load_config
from etftracker.parse import classify_asset, clean_ticker, parse_holdings
from etftracker.pipeline import parse_fetched
from etftracker.sources import Fetched, _from_json_payload, find_link
from etftracker.util import parse_date, to_float

FIX = Path(__file__).parent / "fixtures"
CFG = load_config(Path(__file__).parent.parent / "funds.yaml")


def test_to_float():
    assert to_float("1,234.5") == 1234.5
    assert to_float("$12.30") == 12.3
    assert to_float("(45)") == -45
    assert to_float("3.2%") == 3.2
    assert to_float("-") is None
    assert to_float("") is None


def test_parse_date():
    assert str(parse_date("As of October 16, 2026")) == "2026-10-16"
    assert str(parse_date("10/26/2026")) == "2026-10-26"
    assert str(parse_date("Sequoia_ETF_Holdings_10-16-2026.csv")) == "2026-10-16"
    assert str(parse_date("2026-10-22")) == "2026-10-22"
    assert parse_date("no date here") is None


def test_clean_ticker():
    assert clean_ticker("AMZN US") == "AMZN"
    assert clean_ticker("CSU CN") == "CSU CN"
    assert clean_ticker("RR/ LN") == "RR/ LN"
    assert clean_ticker("") is None


def test_classify_asset():
    assert classify_asset("CHTR", "CHARTER COMMUNICATIONS IN USD 0.001", None) == "equity"
    assert classify_asset("CASH&OTHER", "Cash & Other", None, "Y") == "cash"
    assert classify_asset("RECPAY", "Receivables/Payables", None) == "cash"
    assert classify_asset(None, "BLACKROCK TREASURY TRUST INSTL 62", None) == "cash"
    assert classify_asset("8AMMF0JA0", "US BANK MMDA - USBGFS 9 09/01/2037", None, "Y") == "cash"


def test_eagle_json():
    fund = CFG.fund("EAGL")
    data = (FIX / "eagl_daily_holdings.json").read_bytes()
    fetched = _from_json_payload(fund.source, data, "application/json", fund.source.url)
    holdings, as_of, extra = parse_fetched(fund, fetched)
    assert str(as_of) == "2026-10-22"
    eq = [h for h in holdings if h.asset_type == "equity"]
    assert len(eq) == 27
    amzn = next(h for h in eq if h.ticker == "AMZN")
    assert amzn.shares == 1749784
    assert abs(amzn.weight - 0.0904829) < 1e-6
    assert abs(amzn.market_value - 0.09048286282 * 4976334663.65) < 1
    assert 250 < amzn.price < 265
    cash = [h for h in holdings if h.asset_type == "cash"]
    assert len(cash) == 1 and abs(cash[0].market_value - 134413174.06) < 0.01
    assert abs(cash[0].weight - 134413174.06 / 4976334663.65) < 1e-9
    assert extra["net_assets"] == 4976334663.65
    assert extra["shares_outstanding"] == 136853490


def test_akre_csv():
    fund = CFG.fund("AKRE")
    data = (FIX / "akre_holdings.csv").read_bytes()
    holdings, as_of, extra = parse_fetched(fund, Fetched(data, "text/csv", fund.source.url))
    assert str(as_of) == "2026-10-23"  # file dated 10/26 (Monday) -> previous business day
    eq = [h for h in holdings if h.asset_type == "equity"]
    assert len(eq) == 19
    ma = next(h for h in eq if h.ticker == "MA")
    assert ma.shares == 1136892 and ma.price == 623.6 and abs(ma.weight - 0.143) < 1e-9
    assert {h.ticker for h in holdings if h.asset_type == "cash"} == {"8AMMF0JA0", "CASH&OTHER"}
    assert extra["net_assets"] == 4958939147.51


def test_sequoia_csv():
    fund = CFG.fund("SEQ")
    data = (FIX / "seq_holdings.csv").read_bytes()
    holdings, as_of, _extra = parse_fetched(fund, Fetched(data, "text/csv", "Sequoia_ETF_Holdings_10-16-2026.csv"))
    assert str(as_of) == "2026-10-16"
    eq = [h for h in holdings if h.asset_type == "equity"]
    assert len(eq) == 36
    csu = next(h for h in eq if h.ticker == "CSU CN")
    assert csu.shares == 146860 and abs(csu.weight - 0.0496) < 1e-9
    assert csu.cusip == "B15C4L6"
    assert abs(csu.price - 330886284.11 / 146860) < 1e-6
    assert [h.ticker for h in holdings if h.asset_type == "cash"] == ["RECPAY"]


def test_sequoia_page_link():
    html = (FIX / "seq_filepoint_page.html").read_text()
    link = find_link(html, "https://sequoia.filepoint.live/sequoia-etf", r"Sequoia_ETF_Holdings.*\.csv")
    assert link == "https://sequoia.filepoint.live/assets/data/Sequoia_ETF_Holdings_10-16-2026.csv"


def test_generic_csv_with_preamble_and_percent_weights():
    data = b"""Fund Holdings as of 03/14/2025
Ticker,Security Name,Shares,Market Value,% of Net Assets
AAPL,Apple Inc,1000,"$150,000.00",60.0%
MSFT,Microsoft Corp,500,"$100,000.00",40.0%
"""
    holdings, as_of, _extra = parse_holdings(data)
    assert str(as_of) == "2025-03-14"
    assert [h.ticker for h in holdings] == ["AAPL", "MSFT"]
    assert holdings[0].weight == 0.6 and holdings[0].market_value == 150000 and holdings[0].price == 150


def test_html_table():
    html = b"""<html><body><p>Holdings as of 2025-02-03</p><table>
    <tr><th>Name</th><th>Ticker</th><th>Shares</th><th>CUSIP</th><th>Weight</th></tr>
    <tr><td>Apple</td><td>AAPL</td><td>1,000</td><td>037833100</td><td>55.5%</td></tr>
    <tr><td>Cash</td><td>USD</td><td>12</td><td></td><td>1.0%</td></tr>
    </table></body></html>"""
    holdings, as_of, _extra = parse_holdings(html, content_type="text/html")
    assert str(as_of) == "2025-02-03"
    assert holdings[0].ticker == "AAPL" and holdings[0].cusip == "037833100" and holdings[0].weight == 0.555
    assert holdings[1].asset_type == "cash"


def test_unparseable_raises():
    with pytest.raises(ValueError):
        parse_holdings(b"just some text\nwithout a table\n")


def test_sequoia_live_feed_csv():
    fund = CFG.fund("SEQ")
    data = (FIX / "seq_holdings_live.csv").read_bytes()
    holdings, as_of, _extra = parse_fetched(fund, Fetched(data, "text/csv", "https://filepoint.live/sequoia/get_holdings_file.php"))
    assert str(as_of) == "2026-10-23"
    eq = [h for h in holdings if h.asset_type == "equity"]
    algn = next(h for h in eq if h.ticker == "ALGN")
    assert algn.cusip == "016255101" and algn.shares == 821260 and algn.price == 154.51
    assert abs(algn.weight - 0.018948708371) < 1e-9  # from "Net Assets %", not derived
    assert {h.ticker for h in holdings if h.asset_type == "cash"} == {"RECPAY", "9BBH"}


def test_override_falls_back_when_column_missing():
    data = b"Symbol,Security Identifier,Shares Held,Net Assets %\nAAPL,037833100,10,50\nMSFT,594918104,5,50\n"
    holdings, _as_of, _extra = parse_holdings(data, overrides={"cusip": "Identifier", "weight": "Percentage of Net Assets"})
    assert holdings[0].cusip == "037833100" and holdings[0].weight == 0.5


def test_currency_lines_are_cash():
    assert classify_asset(None, "EURO", None) == "cash"
    assert classify_asset(None, "US DOLLAR", None) == "cash"
    assert classify_asset("9BBH", "BBH SWEEP VEHICLE", None) == "cash"
    assert classify_asset("ERF FP", "Eurofins Scientific S.E.", None) == "equity"
    assert classify_asset("EURN", "Euronav NV", None) == "equity"
