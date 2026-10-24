import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import type { Action, History } from '../api'
import { fmtDate, int, pct, pp, signedInt, signedPct } from '../format'
import ActionChip from './ActionChip'

interface Row { key: string; ticker: string | null; name: string; w0: number | null; w1: number | null; s0: number | null; s1: number | null; adj: number | null; action: Action }

function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b)
  const m = Math.floor(s.length / 2)
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2
}

/** Client-side re-implementation of the flow-adjusted diff for any two snapshot dates. */
export function compareDates(h: History, i0: number, i1: number, threshold: number): { rows: Row[]; flow: number } {
  const ratios: number[] = []
  h.securities.forEach((_, k) => {
    const a = h.shares[k][i0], b = h.shares[k][i1]
    if (a && b && a > 0 && b > 0) ratios.push(b / a)
  })
  const flow = ratios.length >= 3 ? median(ratios) : 1
  const rows: Row[] = []
  h.securities.forEach((sec, k) => {
    const w0 = h.weights[k][i0], w1 = h.weights[k][i1], s0 = h.shares[k][i0], s1 = h.shares[k][i1]
    const held0 = w0 != null || s0 != null, held1 = w1 != null || s1 != null
    if (!held0 && !held1) return
    let action: Action = 'hold', adj: number | null = null
    if (!held0) action = 'new'
    else if (!held1) action = 'exit'
    else if (s0 && s1 != null) {
      adj = s1 / (s0 * flow) - 1
      if (Math.abs(adj) >= threshold && s1 !== s0) action = adj > 0 ? 'add' : 'trim'
    } else if (w0 != null && w1 != null && Math.abs(w1 - w0) >= 0.0025) action = w1 > w0 ? 'add' : 'trim'
    rows.push({ key: sec.key, ticker: sec.ticker, name: sec.name, w0, w1, s0, s1, adj, action })
  })
  const order: Record<Action, number> = { new: 0, exit: 1, add: 2, trim: 3, hold: 4 }
  rows.sort((a, b) => order[a.action] - order[b.action] || Math.abs((b.w1 ?? b.w0 ?? 0) - (b.w0 ?? 0)) - Math.abs((a.w1 ?? a.w0 ?? 0) - (a.w0 ?? 0)))
  return { rows, flow }
}

export default function CompareTool({ history, threshold }: { history: History; threshold: number }) {
  const n = history.dates.length
  const [i1, setI1] = useState(n - 1)
  const [i0, setI0] = useState(Math.max(0, n - 1 - Math.min(5, n - 1)))
  const [onlyChanges, setOnlyChanges] = useState(true)
  const { rows, flow } = useMemo(() => compareDates(history, Math.min(i0, i1), Math.max(i0, i1), threshold), [history, i0, i1, threshold])
  const shown = onlyChanges ? rows.filter((r) => r.action !== 'hold') : rows
  if (n < 2) return <p className="muted">Comparison becomes available once two or more snapshots have been captured.</p>
  const sel = (v: number, set: (x: number) => void, label: string) => (
    <label>{label}
      <select value={v} onChange={(e) => set(Number(e.target.value))}>
        {history.dates.map((d, i) => <option key={d} value={i}>{fmtDate(d)}</option>)}
      </select>
    </label>
  )
  return (
    <div>
      <div className="toolbar">
        {sel(i0, setI0, 'From')}
        {sel(i1, setI1, 'To')}
        <label><input type="checkbox" checked={onlyChanges} onChange={(e) => setOnlyChanges(e.target.checked)} /> Only changes</label>
        <span className="muted small">flow factor {flow.toFixed(4)} · {shown.length} rows</span>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className="data">
          <thead><tr><th>Security</th><th>Change</th><th className="num">Weight from</th><th className="num">Weight to</th><th className="num">Δ weight</th><th className="num">Shares from</th><th className="num">Shares to</th><th className="num">Δ shares</th><th className="num">Δ after flows</th></tr></thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.key}>
                <td><Link to={`/security/${encodeURIComponent(r.key)}`}><b>{r.ticker ?? '—'}</b></Link><div className="name">{r.name}</div></td>
                <td><ActionChip action={r.action} /></td>
                <td className="num">{pct(r.w0)}</td>
                <td className="num">{pct(r.w1)}</td>
                <td className={`num delta ${(r.w1 ?? 0) - (r.w0 ?? 0) > 0 ? 'up' : 'down'}`}>{pp((r.w1 ?? 0) - (r.w0 ?? 0))}</td>
                <td className="num">{int(r.s0)}</td>
                <td className="num">{int(r.s1)}</td>
                <td className="num">{r.s0 != null && r.s1 != null ? signedInt(r.s1 - r.s0) : r.s1 != null ? signedInt(r.s1) : r.s0 != null ? signedInt(-r.s0) : '—'}</td>
                <td className="num">{signedPct(r.adj)}</td>
              </tr>
            ))}
            {!shown.length && <tr><td colSpan={9} className="empty">No changes between these dates.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}
