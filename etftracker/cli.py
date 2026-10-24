from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import load_config
from .store import Store


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="etftracker", description="Track active ETF holdings and trades.")
    ap.add_argument("-c", "--config", default=None, help="path to funds.yaml (default: repo funds.yaml)")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("fetch", help="download today's holdings for every enabled fund and store snapshots")
    p.add_argument("funds", nargs="*", help="tickers to fetch (default: all enabled)")
    p.add_argument("--force", action="store_true", help="overwrite an existing snapshot for the same as-of date")
    p.add_argument("--fail-on-error", action="store_true", help="exit non-zero if any fund failed")

    p = sub.add_parser("build", help="compute trades and export static JSON for the web app")
    p.add_argument("-o", "--out", default="web/public/data", help="output directory for JSON (default: web/public/data)")
    p.add_argument("--sqlite", default=None, help="also (re)build a SQLite database at this path")

    p = sub.add_parser("db", help="(re)build the SQLite database from stored snapshots")
    p.add_argument("-o", "--out", default="data/etftracker.sqlite")

    p = sub.add_parser("status", help="show stored snapshots per fund")

    p = sub.add_parser("import", help="import a holdings file from disk as a snapshot (for backfills/tests)")
    p.add_argument("fund")
    p.add_argument("file")
    p.add_argument("--as-of", default=None, help="override as-of date (YYYY-MM-DD)")
    p.add_argument("--url", default=None, help="source URL to record in metadata")

    argv = list(sys.argv[1:] if argv is None else argv)
    if "-v" in argv[1:] or "--verbose" in argv[1:]:
        argv = ["-v"] + [a for a in argv if a not in ("-v", "--verbose")]
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    config = load_config(args.config)
    store = Store(config.settings.data_dir)

    if args.cmd == "fetch":
        from .pipeline import capture

        wanted = {t.upper() for t in args.funds}
        results = []
        for fund in config.funds:
            if not fund.enabled or (wanted and fund.ticker not in wanted):
                continue
            results.append(capture(fund, config, store, force=args.force))
        errors = 0
        for r in results:
            line = f"{r.fund:6s} {r.status:9s} {r.as_of or '-'} {r.n_holdings:4d} positions {r.message}"
            print(line)
            errors += r.status == "error"
        return 1 if (errors and args.fail_on_error) else 0

    if args.cmd == "build":
        from .export import export_site

        info = export_site(store, config, Path(args.out))
        print(f"exported {len(info['funds'])} funds, {info['trades']} trades -> {args.out}")
        if args.sqlite:
            from .store import build_sqlite

            build_sqlite(store, Path(args.sqlite), {f.ticker: f.__dict__ for f in config.funds}, info["trades_by_fund"])
            print(f"sqlite -> {args.sqlite}")
        return 0

    if args.cmd == "db":
        from .export import fund_analytics
        from .store import build_sqlite

        trades = {}
        for t in store.funds():
            fa = fund_analytics(store, config, t)
            if fa:
                trades[t] = fa["_trades_all"]
        build_sqlite(store, Path(args.out), {f.ticker: f.__dict__ for f in config.funds}, trades)
        print(f"sqlite -> {args.out}")
        return 0

    if args.cmd == "status":
        for t in store.funds():
            dates = store.snapshot_dates(t)
            print(f"{t:6s} {len(dates):4d} snapshots  {dates[0] if dates else '-'} .. {dates[-1] if dates else '-'}")
        return 0

    if args.cmd == "import":
        from datetime import date

        from .models import Snapshot
        from .pipeline import parse_fetched
        from .sources import Fetched
        from .store import sha256
        from .util import now_utc_iso

        fund = config.fund(args.fund)
        data = Path(args.file).read_bytes()
        fetched = Fetched(data, None, args.url or Path(args.file).name)
        if Path(args.file).suffix.lower() == ".json":

            from .sources import _from_json_payload

            fetched = _from_json_payload(fund.source, data, "application/json", args.url or Path(args.file).name)
        holdings, as_of, extra = parse_fetched(fund, fetched)
        if args.as_of:
            as_of = date.fromisoformat(args.as_of)
        if as_of is None:
            print("could not determine as-of date; pass --as-of", file=sys.stderr)
            return 2
        snap = Snapshot(fund=fund.ticker, as_of=as_of, holdings=holdings, fetched_at=now_utc_iso(),
                        source_url=fetched.url, sha256=sha256(data), content_type=fetched.content_type,
                        extra={k: v for k, v in extra.items() if k != "header"})
        store.write_snapshot(snap, data)
        print(f"{fund.ticker}: imported {len(holdings)} positions as of {as_of}")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
