from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "funds.yaml"


@dataclass
class Source:
    """How to obtain a fund's holdings file.

    type:
      - ``csv``:        ``url`` points straight at a CSV/XLSX file.
      - ``page_link``:  fetch ``page`` (HTML), find the first link whose href matches
                        ``link_pattern`` (regex, case-insensitive), download that.
      - ``html_table``: fetch ``page`` and parse the first HTML table whose header
                        row matches ``table_pattern``.
      - ``json``:       GET ``url`` returning JSON; rows at ``records_path``.
      - ``post``:       POST ``form`` to ``url``; the response is JSON (rows at
                        ``records_path``, or a CSV string at that path) or raw CSV.
    Any source may carry a ``fallback`` source used when it fails.
    """

    type: str
    url: str | None = None
    page: str | None = None
    link_pattern: str | None = None
    table_pattern: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    as_of_pattern: str | None = None  # regex applied to page text / file text to find the as-of date
    # JSON sources (``json`` GET or ``post`` form POST): where the rows and the as-of date live.
    records_path: str | None = None  # dotted path to the list of row objects, e.g. "holdings" or "data"
    as_of_path: str | None = None  # dotted path to an as-of date string in the payload
    form: dict[str, str] = field(default_factory=dict)  # form fields for ``post``
    fallback: Source | None = None  # tried when this source errors or yields no rows


@dataclass
class Fund:
    ticker: str
    name: str
    manager: str
    source: Source
    website: str | None = None
    exchange: str | None = None
    inception: str | None = None
    columns: dict[str, str] = field(default_factory=dict)  # normalized field -> source column override
    options: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


@dataclass
class Settings:
    data_dir: Path
    trade_threshold: float = 0.005  # relative share change (after flow adjustment) that counts as a trade
    weight_threshold: float = 0.0025  # absolute weight change (fraction) when shares are unavailable
    flow_threshold: float = 0.0025  # creation/redemption size (fraction of fund) that counts as a flow day
    user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0 Safari/537.36 etftracker/0.1"
    )


@dataclass
class Config:
    funds: list[Fund]
    settings: Settings

    def fund(self, ticker: str) -> Fund:
        for f in self.funds:
            if f.ticker.upper() == ticker.upper():
                return f
        raise KeyError(f"unknown fund {ticker}")


def _source(src: dict) -> Source:
    return Source(
        type=src["type"],
        url=src.get("url"),
        page=src.get("page"),
        link_pattern=src.get("link_pattern"),
        table_pattern=src.get("table_pattern"),
        headers=src.get("headers", {}) or {},
        as_of_pattern=src.get("as_of_pattern"),
        records_path=src.get("records_path"),
        as_of_path=src.get("as_of_path"),
        form={k: str(v) for k, v in (src.get("form", {}) or {}).items()},
        fallback=_source(src["fallback"]) if src.get("fallback") else None,
    )


def load_config(path: Path | str | None = None) -> Config:
    path = Path(path) if path else DEFAULT_CONFIG
    raw = yaml.safe_load(path.read_text()) or {}
    settings_raw = raw.get("settings", {}) or {}
    data_dir = Path(os.environ.get("ETFTRACKER_DATA_DIR") or settings_raw.get("data_dir", "data"))
    if not data_dir.is_absolute():
        data_dir = (path.parent / data_dir).resolve()
    settings = Settings(
        data_dir=data_dir,
        trade_threshold=float(settings_raw.get("trade_threshold", 0.005)),
        weight_threshold=float(settings_raw.get("weight_threshold", 0.0025)),
        flow_threshold=float(settings_raw.get("flow_threshold", 0.0025)),
        user_agent=settings_raw.get("user_agent", Settings.user_agent),
    )
    funds = []
    for item in raw.get("funds", []):
        funds.append(
            Fund(
                ticker=item["ticker"].upper(),
                name=item["name"],
                manager=item.get("manager", ""),
                website=item.get("website"),
                exchange=item.get("exchange"),
                inception=str(item["inception"]) if item.get("inception") else None,
                source=_source(item["source"]),
                columns=item.get("columns", {}) or {},
                options=item.get("options", {}) or {},
                enabled=bool(item.get("enabled", True)),
            )
        )
    return Config(funds=funds, settings=settings)
