import { useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'
import { loadFund, loadIndex, loadSecurities, type FundDetail, type History } from '../api'
import { fmtDate, int, money, pct } from '../format'
import { Status, useAsync } from '../hooks'
import ActionChip from '../components/ActionChip'
import WeightHistoryChart from '../components/WeightHistoryChart'
import TradeList from '../components/TradeList'

/** Merge the one security's row from each fund's history into a single multi-series history keyed by fund. */
function mergeHistories(key: string, funds: FundDetail[]): History {
  const dates = Array.from(new Set(funds.flatMap((f) => f.history.dates))).sort()
  const di = new Map(dates.map((d, i) => [d, i]))
  const securities: History['securities'] = []
  const weights: (number | null)[][] = []
  const shares: (number | null)[][] = []
  for (const f of funds) {
    const i = f.history.securities.findIndex((s) => s.key === key)
    if (i < 0) continue
    securities.push({ key: f.fund.ticker, ticker: f.fund.ticker, name: f.fund.name })
    const w: (number | null)[] = dates.map(() => null), s: (number | null)[] = dates.map(() => null)
    f.history.dates.forEach((d, j) => { w[di.get(d)!] = f.history.weights[i][j]; s[di.get(d)!] = f.history.shares[i][j] })
    weights.push(w); shares.push(s)
  }
  return { dates, securities, weights, shares, cash_weight: [], n_positions: [], net_assets: [], shares_outstanding: [] }
}

export default function SecurityPage() {
  const { key = '' } = useParams()
  const k = decodeURIComponent(key)
  const secs = useAsync(loadSecurities, [])
  const idx = useAsync(loadIndex, [])
  const funds = useAsync(async () => {
    const i = await loadIndex()
    return Promise.all(i.funds.map((f) => loadFund(f.ticker)))
  }, [])
  const entry = secs.data?.securities.find((s) => s.key === k)
  const holders = useMemo(() => (funds.data ?? []).filter((f) => f.history.securities.some((s) => s.key === k)), [funds.data, k])
  const merged = useMemo(() => mergeHistories(k, holders), [k, holders])
  const trades = useMemo(() => holders.flatMap((f) => f.trades.filter((t) => t.key === k)).sort((a, b) => (a.as_of < b.as_of ? 1 : -1)), [holders, k])
  if (!secs.data || !idx.data || !funds.data) return <Status loading={secs.loading || funds.loading} error={secs.error ?? funds.error} />
  const name = entry?.name ?? holders[0]?.history.securities.find((s) => s.key === k)?.name ?? k
  const ticker = entry?.ticker ?? holders[0]?.history.securities.find((s) => s.key === k)?.ticker ?? k.replace(/^T:/, '')
  if (!holders.length) return <div className="empty">No tracked fund holds {ticker} in any captured snapshot.</div>
  return (
    <div>
      <div className="page-head"><h1>{ticker}</h1><span className="sub">{name}</span></div>
      <h2>Held by</h2>
      <div className="card">
        <table className="data">
          <thead><tr><th>Fund</th><th className="num">Weight</th><th className="num">Shares</th><th className="num">Value</th><th>Latest change</th><th>As of</th></tr></thead>
          <tbody>
            {holders.map((f) => {
              const h = f.holdings.find((x) => x.key === k)
              return (
                <tr key={f.fund.ticker}>
                  <td><Link to={`/fund/${f.fund.ticker}`}><b>{f.fund.ticker}</b></Link> <span className="name" style={{ display: 'inline' }}>{f.fund.name}</span></td>
                  <td className="num">{pct(h?.weight)}</td>
                  <td className="num">{int(h?.shares)}</td>
                  <td className="num">{money(h?.market_value)}</td>
                  <td>{h ? <ActionChip action={h.change?.action} /> : <span className="chip exit">✕ no longer held</span>}</td>
                  <td className="muted small">{fmtDate(f.latest_as_of)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <h2>Weight over time, by fund</h2>
      <div className="card"><WeightHistoryChart history={merged} selected={merged.securities.map((s) => s.key)} /></div>
      <h2>Trades in {ticker}</h2>
      <div className="card"><TradeList trades={trades} /></div>
    </div>
  )
}
