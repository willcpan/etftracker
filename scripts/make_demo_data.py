"""Create a synthetic multi-day history from the latest real snapshot of each fund.

Dev-only helper so the web app has trades/history to render before the daily job
has accumulated real snapshots. Writes to a separate data directory (never the
tracked data/ folder) and prints the ``etftracker build`` command to use it.

    python scripts/make_demo_data.py --out /tmp/demo-data --days 30
"""
from __future__ import annotations

import argparse
import copy
import random
from pathlib import Path

from etftracker.config import load_config
from etftracker.models import Holding
from etftracker.store import Store
from etftracker.util import previous_business_day


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rnd = random.Random(args.seed)
    cfg = load_config()
    src = Store(cfg.settings.data_dir)
    dst = Store(Path(args.out))
    for fund in src.funds():
        latest = src.read_snapshot(fund, src.snapshot_dates(fund)[-1])
        # walk backwards in time, generating earlier snapshots from the latest one
        snaps = [latest]
        cur = latest
        for _ in range(args.days):
            prev = copy.deepcopy(cur)
            prev.as_of = previous_business_day(cur.as_of)
            prev.fetched_at = None
            flow = 1 / rnd.uniform(0.985, 1.02)  # undo a creation/redemption
            for h in prev.holdings:
                if h.asset_type != "equity":
                    continue
                if h.shares:
                    h.shares = round(h.shares * flow)
                if h.price:
                    h.price = h.price / rnd.uniform(0.975, 1.025)
            eq = [h for h in prev.holdings if h.asset_type == "equity" and h.shares]
            # occasional manager trades (seen in reverse)
            if eq and rnd.random() < 0.35:
                h = rnd.choice(eq)
                h.shares = round(h.shares / rnd.uniform(0.80, 1.25))
            if eq and rnd.random() < 0.08:  # a position that did not exist earlier
                prev.holdings.remove(rnd.choice(eq))
            if rnd.random() < 0.06:  # a position that was exited since
                t = f"OLD{rnd.randint(1, 99)}"
                prev.holdings.append(Holding(t, f"Former Holding {t}", shares=rnd.randint(50_000, 500_000),
                                             price=rnd.uniform(20, 300)))
            for h in prev.holdings:
                if h.asset_type == "equity" and h.shares is not None and h.price is not None:
                    h.market_value = h.shares * h.price
            total = sum(h.market_value or 0 for h in prev.holdings)
            for h in prev.holdings:
                if h.market_value is not None and total:
                    h.weight = h.market_value / total
            prev.extra = {"net_assets": total}
            snaps.append(prev)
            cur = prev
        for s in snaps:
            raw = s.raw_path and (src.data_dir / s.raw_path)
            dst.write_snapshot(s, raw.read_bytes() if raw and raw.exists() else b"synthetic")
        print(f"{fund}: {len(snaps)} snapshots {snaps[-1].as_of} .. {snaps[0].as_of}")
    print(f"\nnext: etftracker build -o web/public/data  (with settings.data_dir={args.out}, e.g. ETFTRACKER_DATA_DIR)")


if __name__ == "__main__":
    main()
