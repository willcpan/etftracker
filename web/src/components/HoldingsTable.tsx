import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import type { Holding } from '../api'
import { int, money, num, pct, pp, signedPct } from '../format'
import ActionChip from './ActionChip'

type SortKey = 'weight' | 'ticker' | 'shares' | 'price' | 'market_value' | 'weight_change' | 'adj_change'

export default function HoldingsTable({ holdings, maxWeight }: { holdings: Holding[]; maxWeight?: number }) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'weight', dir: -1 })
  const [showCash, setShowCash] = useState(false)
  const rows = useMemo(() => {
    const list = holdings.filter((h) => showCash || h.asset_type === 'equity')
    const val = (h: Holding): number | string | null => {
      switch (sort.key) {
        case 'ticker': return h.ticker ?? h.name
        case 'weight_change': return h.change?.weight_change ?? null
        case 'adj_change': return h.change?.adj_change ?? null
        default: return h[sort.key]
      }
    }
    return [...list].sort((a, b) => {
      const va = val(a), vb = val(b)
      if (va == null && vb == null) return 0
      if (va == null) return 1
      if (vb == null) return -1
      return (va < vb ? -1 : va > vb ? 1 : 0) * sort.dir
    })
  }, [holdings, sort, showCash])
  const max = maxWeight ?? Math.max(...holdings.map((h) => h.weight ?? 0), 0.0001)
  const th = (key: SortKey, label: string, numeric = true) => (
    <th className={numeric ? 'num' : ''} onClick={() => setSort((s) => ({ key, dir: s.key === key ? (s.dir === 1 ? -1 : 1) : key === 'ticker' ? 1 : -1 }))} aria-sort={sort.key === key ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
      {label}{sort.key === key ? (sort.dir === 1 ? ' ↑' : ' ↓') : ''}
    </th>
  )
  return (
    <div>
      <div className="toolbar">
        <label><input type="checkbox" checked={showCash} onChange={(e) => setShowCash(e.target.checked)} /> Show cash & other lines</label>
        <span className="muted small">{rows.length} rows</span>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className="data">
          <thead>
            <tr>
              {th('ticker', 'Security', false)}
              {th('weight', 'Weight')}
              {th('weight_change', 'Δ weight')}
              {th('shares', 'Shares')}
              {th('adj_change', 'Δ shares*')}
              {th('price', 'Price')}
              {th('market_value', 'Value')}
              <th>Change</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((h) => (
              <tr key={h.key}>
                <td>
                  <Link to={`/security/${encodeURIComponent(h.key)}`}><b>{h.ticker ?? '—'}</b></Link>
                  <div className="name" title={h.name}>{h.name}</div>
                </td>
                <td className="num">
                  <span className="wbar" aria-hidden="true"><i style={{ width: `${Math.max(0, (h.weight ?? 0) / max) * 100}%` }} /></span>
                  {pct(h.weight)}
                </td>
                <td className={`num delta ${(h.change?.weight_change ?? 0) > 0 ? 'up' : (h.change?.weight_change ?? 0) < 0 ? 'down' : ''}`}>{pp(h.change?.weight_change)}</td>
                <td className="num">{int(h.shares)}</td>
                <td className={`num delta ${h.change?.action === 'add' ? 'up' : h.change?.action === 'trim' ? 'down' : ''}`}>{h.change?.action === 'new' ? 'new' : signedPct(h.change?.adj_change)}</td>
                <td className="num">{h.price == null ? '—' : num(h.price)}</td>
                <td className="num">{money(h.market_value)}</td>
                <td><ActionChip action={h.change?.action} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">* Share change after removing the fund-wide creation/redemption factor, i.e. the manager's own buying or selling, versus the previous snapshot.</p>
    </div>
  )
}
