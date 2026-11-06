import { Link } from 'react-router-dom'
import type { FlowEvent, Trade } from '../api'
import { fmtDate, num, pp, signedInt, signedMoney, signedPct } from '../format'
import ActionChip from './ActionChip'
import FlowRow from './FlowRow'

function flowContext(t: Trade): string {
  if (t.flow_direction === 'inflow') return ` during a ${signedPct((t.flow_factor ?? 1) - 1, 2)} inflow`
  if (t.flow_direction === 'outflow') return ` during a ${signedPct((t.flow_factor ?? 1) - 1, 2)} outflow`
  return ''
}

function describe(t: Trade): string {
  switch (t.action) {
    case 'new':
      return `opened ${signedInt(t.shares_now).replace('+', '')} shares (${pp(t.weight_now).replace('+', '')} of fund)${flowContext(t)}`
    case 'exit':
      return `sold entire position (${pp(t.weight_prev).replace('+', '')} of fund)${flowContext(t)}`
    case 'kept':
      return `left untouched${flowContext(t)} while other positions were cut pro rata; equivalent to a ${signedPct(t.adj_change)} relative add`
    case 'not_added':
      return `not bought${flowContext(t)} while other positions grew pro rata; equivalent to a ${signedPct(t.adj_change)} relative trim`
    case 'add':
    case 'trim':
      return t.basis === 'shares'
        ? `${signedPct(t.adj_change)} shares beyond flows (${signedInt(t.shares_change)} raw)${flowContext(t)}, weight ${pp(t.weight_change)}`
        : `weight ${pp(t.weight_change)} (no share data)`
    default:
      return ''
  }
}

function PriceLine({ t }: { t: Trade }) {
  if (t.px_est == null) {
    return t.px_close != null && t.action !== 'kept' && t.action !== 'not_added'
      ? <div className="nm">at the day's close ≈ ${num(t.px_close)} (no market bars available)</div>
      : null
  }
  const vsClose = t.px_close ? (t.px_est / t.px_close - 1) * 100 : null
  return (
    <div className="nm" title={`Volume-weighted typical price over ${t.px_days} trading day${t.px_days === 1 ? '' : 's'} (${t.px_symbol}); range is the window's low to high`}>
      est. fill ≈ <b>${num(t.px_est)}</b> (range ${num(t.px_low)}–${num(t.px_high)}
      {t.px_days && t.px_days > 1 ? `, ${t.px_days} days` : ''})
      {t.px_close != null && vsClose != null ? `, close ${num(t.px_close)} (${vsClose >= 0 ? '+' : ''}${vsClose.toFixed(1)}%)` : ''}
    </div>
  )
}

type Row = { kind: 'trade'; t: Trade } | { kind: 'flow'; f: FlowEvent }

export default function TradeList({ trades, flows = [], showFund = true, limit }: { trades: Trade[]; flows?: FlowEvent[]; showFund?: boolean; limit?: number }) {
  // Interleave: a flow row heads each (fund, date) group that has trades or a meaningful flow.
  const rows: Row[] = []
  const flowKey = (fund: string, d: string) => `${fund}|${d}`
  const flowMap = new Map(flows.map((f) => [flowKey(f.fund, f.as_of), f]))
  const groups = new Map<string, Trade[]>()
  for (const t of trades) {
    const k = flowKey(t.fund, t.as_of)
    if (!groups.has(k)) groups.set(k, [])
    groups.get(k)!.push(t)
  }
  const keys = new Set<string>([...groups.keys(), ...flows.filter((f) => f.flow_direction !== 'none').map((f) => flowKey(f.fund, f.as_of))])
  const ordered = [...keys].sort((a, b) => {
    const [fa, da] = a.split('|'), [fb, db] = b.split('|')
    return da === db ? (fa < fb ? -1 : 1) : da < db ? 1 : -1
  })
  for (const k of ordered) {
    const f = flowMap.get(k)
    if (f) rows.push({ kind: 'flow', f })
    for (const t of groups.get(k) ?? []) rows.push({ kind: 'trade', t })
  }
  const shown = limit ? rows.slice(0, limit) : rows
  if (!shown.length) return <div className="empty">No trades detected in this window.</div>
  return (
    <div>
      {shown.map((r, i) =>
        r.kind === 'flow' ? (
          <FlowRow key={`f-${r.f.fund}-${r.f.as_of}`} f={r.f} showFund={showFund} />
        ) : (
          <div className="trade-row" key={`${r.t.fund}-${r.t.as_of}-${r.t.key}-${i}`}>
            <span className="date" title={`vs. ${fmtDate(r.t.prev_as_of)}`}>{fmtDate(r.t.as_of)}</span>
            {showFund ? <Link className="fund" to={`/fund/${r.t.fund}`}>{r.t.fund}</Link> : <span className="fund muted">{r.t.fund}</span>}
            <ActionChip action={r.t.action} short />
            <span className="sec">
              <Link to={`/security/${encodeURIComponent(r.t.key)}`}><b>{r.t.ticker ?? '—'}</b></Link>{' '}
              <span className="nm">{r.t.name}</span>
              <div className="nm">{describe(r.t)}</div>
              {(r.t.action === 'add' || r.t.action === 'trim' || r.t.action === 'new' || r.t.action === 'exit') && <PriceLine t={r.t} />}
            </span>
            <span className="val" title={r.t.px_est != null ? 'Estimated dollar value at the estimated fill price' : 'Estimated dollar value at the fund file\'s closing price'}>{signedMoney(r.t.est_value)}</span>
          </div>
        ),
      )}
    </div>
  )
}
