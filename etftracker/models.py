from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

NORMALIZED_COLUMNS = [
    "ticker",
    "name",
    "cusip",
    "isin",
    "sedol",
    "asset_type",
    "shares",
    "price",
    "market_value",
    "weight",
]


@dataclass
class Holding:
    ticker: str | None
    name: str
    cusip: str | None = None
    isin: str | None = None
    sedol: str | None = None
    asset_type: str = "equity"  # equity | cash | other
    shares: float | None = None
    price: float | None = None
    market_value: float | None = None
    weight: float | None = None  # fraction of net assets, e.g. 0.0512

    @property
    def key(self) -> str:
        """Stable identity used to match a position across snapshots."""
        if self.ticker:
            return f"T:{self.ticker}"
        if self.cusip:
            return f"C:{self.cusip}"
        if self.isin:
            return f"I:{self.isin}"
        return "N:" + " ".join(self.name.upper().split())

    def to_row(self) -> dict:
        d = asdict(self)
        return {k: d[k] for k in NORMALIZED_COLUMNS}


@dataclass
class Snapshot:
    fund: str
    as_of: date
    holdings: list[Holding]
    fetched_at: str | None = None
    source_url: str | None = None
    sha256: str | None = None
    content_type: str | None = None
    raw_path: str | None = None
    extra: dict = field(default_factory=dict)  # net_assets, shares_outstanding, etc.

    @property
    def equities(self) -> list[Holding]:
        return [h for h in self.holdings if h.asset_type == "equity"]

    def total_market_value(self) -> float | None:
        vals = [h.market_value for h in self.holdings if h.market_value is not None]
        return sum(vals) if vals else None
