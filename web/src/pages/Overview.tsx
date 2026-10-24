import { Link } from 'react-router-dom'
import { loadIndex, type FundSummary } from '../api'
import { daysAgoIso, fmtDate, fmtDateTime, money, pct } from '../format'
import { Status, useAsync } from '../hooks'
import TradeList from '../components/TradeList'
import { flowLabel } from '../format'

function FundCard({ f }: { f: FundSummary }) {
  const c = f.latest_changes
  const nChanges = c.new + c.exit + c.add + c.trim + c.kept + c.not_added
  const max = Math.max(...f.top_holdings.map((h) => h.weight ?? 0), 0.0001)
  return (
    <Link to={`/fund/${f.ticker}`} className="card fund-card">
      <div className="title">
        <span><span className="ticker">{f.ticker}</span> <span className="name">{f.name}</span></span>
        <span className="muted small">as of {fmtDate(f.latest_as_of)}</span>
      </div>
      <div className="kv">
        <span><b>{money(f.net_assets)}</b> net assets</span>
        <span><b>{f.n_positions}</b> positions</span>
        <span><b>{pct(f.cash_weight, 1)}</b> cash</span>
        <span><b>{f.n_snapshots}</b> snapshots</span>
      </div>
      <div className="chips" aria-label="Changes versus previous snapshot">
        {f.prev_as_of == null ? <span className="chip hold">first snapshot</span> : nChanges === 0 ? <span className="chip hold">no trades vs {fmtDate(f.prev_as_of)}</span> : null}
        {c.new > 0 && <span className="chip new">✚ {c.new} new</span>}
        {c.add > 0 && <span className="chip add">▲ {c.add} added</span>}
        {c.trim > 0 && <span className="chip trim">▼ {c.trim} trimmed</span>}
        {c.exit > 0 && <span className="chip exit">✕ {c.exit} exited</span>}
        {c.kept > 0 && <span className="chip kept">◆ {c.kept} kept</span>}
        {c.not_added > 0 && <span className="chip not_added">◇ {c.not_added} not added</span>}
      </div>
      {f.latest_flow && f.prev_as_of && (
        <div className="small muted">Flows vs {fmtDate(f.prev_as_of)}: {flowLabel(f.latest_flow.flow_direction, f.latest_flow.flow_pct)}{f.latest_flow.flow_direction !== 'none' && f.latest_flow.flow_value != null ? ` (≈ ${money(Math.abs(f.latest_flow.flow_value))})` : ''}</div>
      )}
      <ul className="top-list" aria-label="Top holdings">
        {f.top_holdings.slice(0, 5).map((h) => (
          <li key={h.ticker ?? h.name}>
            <b>{h.ticker ?? '—'}</b>
            <span className="bar" aria-hidden="true"><i style={{ width: `${((h.weight ?? 0) / max) * 100}%` }} /></span>
            <span className="num">{pct(h.weight, 1)}</span>
          </li>
        ))}
      </ul>
    </Link>
  )
}

export default function Overview() {
  const { data, loading, error } = useAsync(loadIndex, [])
  if (!data) return <Status loading={loading} error={error} />
  const cutoff = daysAgoIso(30)
  const recent30 = data.recent_activity.filter((t) => t.as_of >= cutoff)
  const latest = data.funds.map((f) => f.latest_as_of).sort().at(-1)
  return (
    <div>
      <div className="page-head">
        <h1>Active ETF holdings tracker</h1>
        <span className="sub">What concentrated active managers are buying and selling, from their daily holdings files.</span>
      </div>
      <div className="stat-row">
        <div className="stat"><div className="lbl">Funds tracked</div><div className="val">{data.funds.length}</div></div>
        <div className="stat"><div className="lbl">Distinct securities</div><div className="val">{data.n_securities}</div></div>
        <div className="stat"><div className="lbl">Trades, last 30 days</div><div className="val">{recent30.length}</div></div>
        <div className="stat"><div className="lbl">Latest holdings</div><div className="val" style={{ fontSize: 18 }}>{fmtDate(latest)}</div><div className="sub">updated {fmtDateTime(data.generated_at)}</div></div>
      </div>
      <div className="grid">
        {data.funds.map((f) => <FundCard key={f.ticker} f={f} />)}
      </div>
      <h2>Recent activity</h2>
      <div className="card">
        <TradeList trades={data.recent_activity} flows={data.recent_flows} limit={30} />
        {data.recent_activity.length > 25 && <p className="small" style={{ margin: '12px 0 0' }}><Link to="/activity">See all activity →</Link></p>}
      </div>
    </div>
  )
}
