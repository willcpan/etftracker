"""On-disk layout and SQLite loading.

data/
  raw/<TICKER>/<as_of>.<ext>          exact bytes as downloaded
  raw/<TICKER>/<as_of>.meta.json      provenance (url, sha256, fetched_at, content type)
  normalized/<TICKER>/<as_of>.csv     one row per position in the normalized schema

The normalized CSVs are the source of truth that lives in git; the SQLite database
is a derived artifact (``etftracker db``) for ad-hoc analysis.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from datetime import date
from pathlib import Path

from .models import NORMALIZED_COLUMNS, Holding, Snapshot
from .util import to_float


def ext_for(content_type: str | None, url: str | None, data: bytes) -> str:
    ct = (content_type or "").lower()
    u = (url or "").lower().split("?")[0]
    if data[:4] == b"PK\x03\x04" or u.endswith(".xlsx") or "spreadsheetml" in ct:
        return "xlsx"
    if "json" in ct or u.endswith(".json"):
        return "json"
    if "html" in ct or u.endswith((".html", ".htm")):
        return "html"
    return "csv"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.raw_dir = self.data_dir / "raw"
        self.norm_dir = self.data_dir / "normalized"

    # ---- writing -----------------------------------------------------------------
    def existing_sha(self, fund: str, as_of: date) -> str | None:
        meta = self.raw_dir / fund / f"{as_of.isoformat()}.meta.json"
        if meta.exists():
            return json.loads(meta.read_text()).get("sha256")
        return None

    def latest_sha(self, fund: str) -> str | None:
        dates = self.snapshot_dates(fund)
        return self.existing_sha(fund, dates[-1]) if dates else None

    def write_snapshot(self, snap: Snapshot, raw: bytes) -> tuple[Path, Path]:
        fund_raw = self.raw_dir / snap.fund
        fund_norm = self.norm_dir / snap.fund
        fund_raw.mkdir(parents=True, exist_ok=True)
        fund_norm.mkdir(parents=True, exist_ok=True)
        ext = ext_for(snap.content_type, snap.source_url, raw)
        stem = snap.as_of.isoformat()
        raw_path = fund_raw / f"{stem}.{ext}"
        raw_path.write_bytes(raw)
        meta = {
            "fund": snap.fund,
            "as_of": stem,
            "fetched_at": snap.fetched_at,
            "source_url": snap.source_url,
            "content_type": snap.content_type,
            "sha256": snap.sha256 or sha256(raw),
            "bytes": len(raw),
            "n_holdings": len(snap.holdings),
            "total_market_value": snap.total_market_value(),
            **{k: v for k, v in snap.extra.items() if k not in ("header",)},
        }
        (fund_raw / f"{stem}.meta.json").write_text(json.dumps(meta, indent=1, default=str) + "\n")
        norm_path = fund_norm / f"{stem}.csv"
        with norm_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=NORMALIZED_COLUMNS)
            w.writeheader()
            for h in snap.holdings:
                row = h.to_row()
                for k in ("shares", "price", "market_value", "weight"):
                    if row[k] is not None:
                        row[k] = f"{row[k]:.10g}" if k != "weight" else f"{row[k]:.8f}"
                w.writerow(row)
        snap.raw_path = str(raw_path.relative_to(self.data_dir))
        return raw_path, norm_path

    # ---- reading -----------------------------------------------------------------
    def funds(self) -> list[str]:
        if not self.norm_dir.exists():
            return []
        return sorted(p.name for p in self.norm_dir.iterdir() if p.is_dir())

    def snapshot_dates(self, fund: str) -> list[date]:
        d = self.norm_dir / fund
        if not d.exists():
            return []
        return sorted(date.fromisoformat(p.stem) for p in d.glob("????-??-??.csv"))

    def read_meta(self, fund: str, as_of: date) -> dict:
        p = self.raw_dir / fund / f"{as_of.isoformat()}.meta.json"
        return json.loads(p.read_text()) if p.exists() else {}

    def read_snapshot(self, fund: str, as_of: date) -> Snapshot:
        p = self.norm_dir / fund / f"{as_of.isoformat()}.csv"
        holdings: list[Holding] = []
        with p.open(newline="") as f:
            for row in csv.DictReader(f):
                holdings.append(
                    Holding(
                        ticker=row.get("ticker") or None,
                        name=row.get("name") or "",
                        cusip=row.get("cusip") or None,
                        isin=row.get("isin") or None,
                        sedol=row.get("sedol") or None,
                        asset_type=row.get("asset_type") or "equity",
                        shares=to_float(row.get("shares")),
                        price=to_float(row.get("price")),
                        market_value=to_float(row.get("market_value")),
                        weight=to_float(row.get("weight")),
                    )
                )
        meta = self.read_meta(fund, as_of)
        return Snapshot(
            fund=fund,
            as_of=as_of,
            holdings=holdings,
            fetched_at=meta.get("fetched_at"),
            source_url=meta.get("source_url"),
            sha256=meta.get("sha256"),
            content_type=meta.get("content_type"),
            extra={k: v for k, v in meta.items() if k in ("net_assets", "shares_outstanding", "nav")},
        )

    def read_all(self, fund: str) -> list[Snapshot]:
        return [self.read_snapshot(fund, d) for d in self.snapshot_dates(fund)]


SCHEMA = """
CREATE TABLE IF NOT EXISTS funds (
  ticker TEXT PRIMARY KEY, name TEXT, manager TEXT, website TEXT
);
CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY, fund TEXT NOT NULL, as_of TEXT NOT NULL, fetched_at TEXT,
  source_url TEXT, sha256 TEXT, n_holdings INTEGER, total_market_value REAL, net_assets REAL,
  UNIQUE(fund, as_of)
);
CREATE TABLE IF NOT EXISTS holdings (
  snapshot_id INTEGER NOT NULL REFERENCES snapshots(id), fund TEXT NOT NULL, as_of TEXT NOT NULL,
  key TEXT NOT NULL, ticker TEXT, name TEXT, cusip TEXT, isin TEXT, sedol TEXT, asset_type TEXT,
  shares REAL, price REAL, market_value REAL, weight REAL
);
CREATE INDEX IF NOT EXISTS holdings_fund_date ON holdings(fund, as_of);
CREATE INDEX IF NOT EXISTS holdings_key ON holdings(key, fund, as_of);
CREATE TABLE IF NOT EXISTS trades (
  fund TEXT NOT NULL, as_of TEXT NOT NULL, prev_as_of TEXT NOT NULL, key TEXT NOT NULL,
  ticker TEXT, name TEXT, action TEXT NOT NULL, basis TEXT,
  shares_prev REAL, shares_now REAL, shares_change REAL, adj_change REAL,
  weight_prev REAL, weight_now REAL, weight_change REAL, est_value REAL, flow_factor REAL
);
CREATE INDEX IF NOT EXISTS trades_fund_date ON trades(fund, as_of);
"""


def build_sqlite(store: Store, db_path: Path, funds_meta: dict[str, dict], trades_by_fund: dict[str, list[dict]]) -> None:
    """(Re)build the SQLite database from normalized CSVs + computed trades."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    for t, m in funds_meta.items():
        con.execute("INSERT INTO funds VALUES (?,?,?,?)", (t, m.get("name"), m.get("manager"), m.get("website")))
    for fund in store.funds():
        for snap in store.read_all(fund):
            cur = con.execute(
                "INSERT INTO snapshots(fund, as_of, fetched_at, source_url, sha256, n_holdings, total_market_value, net_assets)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (fund, snap.as_of.isoformat(), snap.fetched_at, snap.source_url, snap.sha256, len(snap.holdings),
                 snap.total_market_value(), snap.extra.get("net_assets")),
            )
            sid = cur.lastrowid
            con.executemany(
                "INSERT INTO holdings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(sid, fund, snap.as_of.isoformat(), h.key, h.ticker, h.name, h.cusip, h.isin, h.sedol, h.asset_type,
                  h.shares, h.price, h.market_value, h.weight) for h in snap.holdings],
            )
    for fund, trades in trades_by_fund.items():
        con.executemany(
            "INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(fund, t["as_of"], t["prev_as_of"], t["key"], t["ticker"], t["name"], t["action"], t["basis"],
              t["shares_prev"], t["shares_now"], t["shares_change"], t["adj_change"], t["weight_prev"],
              t["weight_now"], t["weight_change"], t["est_value"], t["flow_factor"]) for t in trades],
        )
    con.commit()
    con.close()
