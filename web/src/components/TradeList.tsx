import { Link } from 'react-router-dom'
import type { Trade } from '../api'
import { fmtDate, pp, signedInt, signedMoney, signedPct } from '../format'
import ActionChip from './ActionChip'

function describe(t: Trade): string {
  switch (t.action) {
    case 'new':
      return `opened ${signedInt(t.shares_now).replace('+', '')} shares (${pp(t.weight_now).replace('+', '')} of fund)`
    case 'exit':
      return `sold entire position (${pp(t.weight_prev).replace('+', '')} of fund)`
    case 'add':
    case 'trim':
      return t.basis === 'shares'
        ? `${signedPct(t.adj_change)} shares after flows (${signedInt(t.shares_change)}), weight ${pp(t.weight_change)}`
        : `weight ${pp(t.weight_change)} (no share data)`
    default:
      return ''
  }
}

export default function TradeList({ trades, showFund = true, limit }: { trades: Trade[]; showFund?: boolean; limit?: number }) {
  const rows = limit ? trades.slice(0, limit) : trades
  if (!rows.length) return <div className="empty">No trades detected in this window.</div>
  return (
    <div>
      {rows.map((t, i) => (
        <div className="trade-row" key={`${t.fund}-${t.as_of}-${t.key}-${i}`}>
          <span className="date" title={`vs. ${fmtDate(t.prev_as_of)}`}>{fmtDate(t.as_of)}</span>
          {showFund ? <Link className="fund" to={`/fund/${t.fund}`}>{t.fund}</Link> : <span className="fund muted">{t.fund}</span>}
          <ActionChip action={t.action} short />
          <span className="sec">
            <Link to={`/security/${encodeURIComponent(t.key)}`}><b>{t.ticker ?? '—'}</b></Link>{' '}
            <span className="nm">{t.name}</span>
            <div className="nm">{describe(t)}</div>
          </span>
          <span className="val" title="Estimated dollar value of the trade">{signedMoney(t.est_value)}</span>
        </div>
      ))}
    </div>
  )
}
