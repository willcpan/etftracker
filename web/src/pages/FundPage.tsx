import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { loadFund } from '../api'
import { fmtDate, fmtDateTime, money, pct } from '../format'
import { Status, useAsync } from '../hooks'
import HoldingsTable from '../components/HoldingsTable'
import TradeList from '../components/TradeList'
import WeightHistoryChart from '../components/WeightHistoryChart'
import CompareTool from '../components/CompareTool'

export default function FundPage() {
  const { ticker = '' } = useParams()
  const { data, loading, error } = useAsync(() => loadFund(ticker.toUpperCase()), [ticker])
  const [selected, setSelected] = useState<string[] | null>(null)
  const [mode, setMode] = useState<'weight' | 'shares'>('weight')
  const defaultSel = useMemo(() => data?.history.securities.slice(0, 6).map((s) => s.key) ?? [], [data])
  if (!data) return <Status loading={loading} error={error} />
  const sel = selected ?? defaultSel
  const c = data.latest_changes
  const toggle = (k: string) => setSelected((cur) => {
    const base = cur ?? defaultSel
    if (base.includes(k)) return base.filter((x) => x !== k)
    if (base.length >= 8) return base
    return [...base, k]
  })
  const latestTrades = data.trades.filter((t) => t.as_of === data.latest_as_of)
  return (
    <div>
      <div className="page-head">
        <h1>{data.fund.ticker} <span className="muted" style={{ fontWeight: 400 }}>{data.fund.name}</span></h1>
        <span className="sub">{data.fund.manager}{data.fund.exchange ? ` · ${data.fund.exchange}` : ''}{data.fund.inception ? ` · since ${fmtDate(data.fund.inception)}` : ''}{data.fund.website && <> · <a href={data.fund.website} target="_blank" rel="noreferrer">fund site ↗</a></>}</span>
      </div>
      <div className="stat-row">
        <div className="stat"><div className="lbl">Holdings as of</div><div className="val" style={{ fontSize: 18 }}>{fmtDate(data.latest_as_of)}</div><div className="sub">captured {fmtDateTime(data.fetched_at)}</div></div>
        <div className="stat"><div className="lbl">Net assets</div><div className="val">{money(data.net_assets)}</div></div>
        <div className="stat"><div className="lbl">Positions</div><div className="val">{data.n_positions}</div><div className="sub">{pct(data.cash_weight, 1)} cash</div></div>
        <div className="stat"><div className="lbl">Snapshots</div><div className="val">{data.n_snapshots}</div><div className="sub">since {fmtDate(data.history.dates[0])}</div></div>
        <div className="stat"><div className="lbl">Flow factor</div><div className="val">{data.flow_factor == null ? '—' : data.flow_factor.toFixed(4)}</div><div className="sub">share scaling from creations/redemptions</div></div>
      </div>

      <h2>Changes vs. {data.prev_as_of ? fmtDate(data.prev_as_of) : 'previous snapshot'}</h2>
      <div className="card">
        {data.prev_as_of == null ? (
          <p className="muted" style={{ margin: 0 }}>Only one snapshot so far. Trades appear once the next day's holdings are captured.</p>
        ) : (
          <>
            <div className="chips" style={{ marginBottom: 12 }}>
              <span className="chip new">✚ {c.new} new</span>
              <span className="chip add">▲ {c.add} added</span>
              <span className="chip trim">▼ {c.trim} trimmed</span>
              <span className="chip exit">✕ {c.exit} exited</span>
              <span className="muted small">threshold {pct(data.trade_threshold, 1)} flow-adjusted share change</span>
            </div>
            <TradeList trades={latestTrades} showFund={false} />
          </>
        )}
      </div>

      <h2>Holdings</h2>
      <div className="card"><HoldingsTable holdings={data.holdings} /></div>

      <h2>Position history</h2>
      <div className="card">
        <div className="toolbar">
          <span className="seg" role="group" aria-label="Measure">
            <button className={mode === 'weight' ? 'active' : ''} onClick={() => setMode('weight')}>Weight</button>
            <button className={mode === 'shares' ? 'active' : ''} onClick={() => setMode('shares')}>Shares</button>
          </span>
          <span className="muted small">Up to 8 holdings. Click to toggle.</span>
        </div>
        <div className="chips" style={{ marginBottom: 8 }}>
          {data.history.securities.slice(0, 40).map((s) => (
            <button key={s.key} className={`chip ${sel.includes(s.key) ? 'new' : 'hold'}`} style={{ cursor: 'pointer', background: sel.includes(s.key) ? undefined : 'transparent' }} onClick={() => toggle(s.key)} aria-pressed={sel.includes(s.key)}>{s.ticker ?? s.name}</button>
          ))}
        </div>
        <WeightHistoryChart history={data.history} selected={sel} mode={mode} />
      </div>

      <h2>Compare any two dates</h2>
      <div className="card"><CompareTool history={data.history} threshold={data.trade_threshold} /></div>

      <h2>Trade log</h2>
      <div className="card"><TradeList trades={data.trades} showFund={false} limit={300} /></div>
      {data.source_url && <p className="muted small">Source: <a href={data.source_url} target="_blank" rel="noreferrer">{data.source_url}</a></p>}
    </div>
  )
}
