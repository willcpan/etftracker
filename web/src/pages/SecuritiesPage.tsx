import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { loadSecurities } from '../api'
import { pct } from '../format'
import { Status, useAsync } from '../hooks'
import ActionChip from '../components/ActionChip'

export default function SecuritiesPage() {
  const { data, loading, error } = useAsync(loadSecurities, [])
  const [q, setQ] = useState('')
  const [minFunds, setMinFunds] = useState(1)
  const rows = useMemo(() => {
    if (!data) return []
    const needle = q.trim().toLowerCase()
    return data.securities.filter((s) => s.funds.length >= minFunds && (!needle || (s.ticker ?? '').toLowerCase().includes(needle) || s.name.toLowerCase().includes(needle)))
  }, [data, q, minFunds])
  if (!data) return <Status loading={loading} error={error} />
  const funds = Array.from(new Set(data.securities.flatMap((s) => s.funds.map((f) => f.fund)))).sort()
  return (
    <div>
      <div className="page-head"><h1>Portfolio overlap</h1><span className="sub">Which securities the tracked managers own in common, by latest weight.</span></div>
      <div className="card">
        <div className="toolbar">
          <label>Search <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="ticker or name" /></label>
          <span className="seg" role="group" aria-label="Held by at least">
            {[1, 2, 3].map((n) => <button key={n} className={minFunds === n ? 'active' : ''} onClick={() => setMinFunds(n)}>{n}+ funds</button>)}
          </span>
          <span className="muted small">{rows.length} securities</span>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table className="data">
            <thead><tr><th>Security</th><th className="num">Funds</th>{funds.map((f) => <th key={f} className="num">{f}</th>)}<th className="num">Combined</th></tr></thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.key}>
                  <td><Link to={`/security/${encodeURIComponent(s.key)}`}><b>{s.ticker ?? '—'}</b></Link><div className="name">{s.name}</div></td>
                  <td className="num">{s.funds.length}</td>
                  {funds.map((f) => {
                    const h = s.funds.find((x) => x.fund === f)
                    return <td key={f} className="num">{h ? <>{pct(h.weight)} <ActionChip action={h.action} short /></> : <span className="muted">·</span>}</td>
                  })}
                  <td className="num">{pct(s.funds.reduce((a, b) => a + b.weight, 0))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
