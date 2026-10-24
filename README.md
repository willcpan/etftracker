# etftracker

Tracks the daily holdings of concentrated active ETFs and works out what their managers
are buying and selling. Currently wired up for:

| Ticker | Fund | Holdings source |
|---|---|---|
| EAGL | Eagle Capital Select Equity ETF | JSON basket feed behind eaglecap.com's daily-holdings page |
| AKRE | Akre Focus ETF | US Bank style CSV hosted on FilePoint (akre.filepoint.live) |
| SEQ | Sequoia ETF | FilePoint live feed (Ultimus), falling back to the CSV linked from sequoia.filepoint.live |

Adding a fund is one entry in [`funds.yaml`](funds.yaml).

## How it works

```
GitHub Actions (daily)            git (main)                     GitHub Pages
┌─────────────────────┐   commit  ┌──────────────────────┐  build  ┌──────────────┐
│ etftracker fetch    │ ────────▶ │ data/raw/<T>/<date>  │ ──────▶ │ web/ (React) │
│  download + parse   │           │ data/normalized/...  │         │ static JSON  │
└─────────────────────┘           └──────────────────────┘         └──────────────┘
```

1. **Fetch** (`etftracker fetch`). For every fund in `funds.yaml` the configured source is
   downloaded (direct CSV/XLSX, JSON API, POST feed, a link discovered on a page, or an HTML
   table), parsed with column heuristics into a normalized schema, and stored as
   * `data/raw/<TICKER>/<as-of>.<ext>` — the exact bytes received, plus `.meta.json` provenance
     (URL, sha256, fetch time, net assets, ...), and
   * `data/normalized/<TICKER>/<as-of>.csv` — one row per position: ticker, name, cusip, isin,
     sedol, asset_type, shares, price, market_value, weight.

   A file whose bytes match the previous snapshot is skipped, so running the job several times
   a day is harmless. The normalized CSVs in git are the source of truth.

2. **Analyze** (`etftracker build`). Consecutive snapshots of each fund are diffed. Because
   creations and redemptions scale every position's share count, the median share ratio across
   positions is taken as the *flow factor* and divided out first; a position whose share count
   then moved by more than the fund's `trade_threshold` is reported as an **add** or **trim**,
   with **new** and **exit** for positions appearing or disappearing. The estimated dollar value
   of each trade is the flow-adjusted share change times the day's price. Results are written as
   static JSON (`index.json`, `activity.json`, `securities.json`, `funds/<T>.json`).

3. **Web app** (`web/`, Vite + React). Reads that JSON. Pages: fund overview with latest
   changes; per-fund holdings table, position-history chart, any-two-dates comparison and trade
   log; cross-fund activity feed with filters; portfolio overlap; per-security view.

## Daily job and deployment

* [`.github/workflows/daily.yml`](.github/workflows/daily.yml) runs at 07:15 and 13:15 UTC
  Tuesday–Saturday (fund files are refreshed in the evening US Eastern after each close),
  commits new snapshots to `main`, and then deploys the site.
* [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) rebuilds and deploys the site on
  every push to `main`.
* [`.github/workflows/ci.yml`](.github/workflows/ci.yml) lints, tests, and builds on every push.

**One-time setup after merging:** in the repository settings open *Pages* and set *Source* to
"GitHub Actions". The site then appears at `https://<owner>.github.io/<repo>/`. The daily job
pushes to `main` with the built-in `GITHUB_TOKEN`; if you enable branch protection on `main`,
allow that bot to push or point the job at a `data` branch.

## Local use

```bash
uv sync --all-extras              # python deps (or: pip install -e ".[dev]")
uv run etftracker fetch           # download today's files into data/
uv run etftracker status          # snapshots per fund
uv run etftracker build           # -> web/public/data/*.json
uv run etftracker db              # -> data/etftracker.sqlite (funds, snapshots, holdings, trades)
uv run pytest

cd web && npm ci && npm run dev   # http://localhost:5173
```

Other commands: `etftracker import <TICKER> <file> [--as-of YYYY-MM-DD]` loads a holdings file
from disk (backfills), and `etftracker fetch EAGL --force` re-fetches one fund.

To exercise the UI before the job has accumulated history, generate synthetic snapshots from the
latest real ones (never written to the tracked `data/` folder):

```bash
uv run python scripts/make_demo_data.py --out /tmp/demo-data --days 30
ETFTRACKER_DATA_DIR=/tmp/demo-data uv run etftracker build
```

## Adding a fund

Append to `funds.yaml`:

```yaml
  - ticker: XYZ
    name: Example Active ETF
    manager: Example Capital
    website: https://example.com/xyz
    source:
      type: csv                       # csv | json | post | page_link | html_table
      url: https://example.com/xyz-holdings.csv
    columns:                          # only if the header heuristics need help
      weight: "% of Net Assets"
    options:
      as_of_adjust: prev_business_day # if the file is stamped with the next trading date
      trade_threshold: 0.01           # per-fund override
```

Most ETF holdings files are recognised without `columns`: ticker/symbol, name/description,
cusip/isin/sedol, shares/quantity, price, market value, weight/% of net assets, money-market
flags, and an "as of" date in a preamble line, a date column, or the file name. See
[`etftracker/parse.py`](etftracker/parse.py) for the synonym table. Run
`uv run etftracker fetch XYZ -v` and check `data/normalized/XYZ/` to verify.

## Caveats

* Trade detection is an estimate from end-of-day files. Rounded basket quantities, corporate
  actions, and in-kind baskets can produce small false positives; thresholds are per fund.
* Weights and prices are whatever the issuer publishes (foreign lines are typically already in USD).
* Sequoia's FilePoint page is currently hand-maintained with a static CSV while its live feed
  is being connected; the adapter tries the feed first and falls back to the static file.
