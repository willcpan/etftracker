import { Link } from 'react-router-dom'
import type { FlowEvent } from '../api'
import { fmtDate, money, signedPct } from '../format'

function Tickers({ list, limit = 6 }: { list: string[]; limit?: number }) {
  if (!list.length) return null
  const shown = list.slice(0, limit)
  return (
    <span className="tk">
      {shown.map((t) => <Link key={t} to={`/security/${encodeURIComponent('T:' + t)}`}>{t}</Link>)}
      {list.length > limit && <span className="muted">+{list.length - limit} more</span>}
    </span>
  )
}

/** A one-line account of a creation/redemption day and how the manager handled it. */
export function flowSentence(f: FlowEvent): string {
  const c = f.counts
  const basis = f.flow_basis === 'shares_outstanding' ? 'from shares outstanding' : f.flow_basis === 'median' ? 'estimated from position sizes' : ''
  if (f.flow_direction === 'none') return `No meaningful creations or redemptions (${signedPct(f.flow_pct, 2)} ${basis}).`
  const dir = f.flow_direction === 'inflow' ? 'Inflow' : 'Outflow'
  const amt = f.flow_value != null ? `≈ ${money(Math.abs(f.flow_value))} ` : ''
  const head = `${dir} ${amt}(${signedPct(f.flow_pct, 2)} ${basis}).`
  const verb = f.flow_direction === 'inflow' ? 'grew' : 'shrank'
  switch (f.flow_handling) {
    case 'selective':
      return `${head} Met ${f.flow_direction === 'inflow' ? 'by buying' : 'by selling'} a few names or with cash: ${f.n_unchanged} of ${f.n_positions} positions untouched.`
    case 'pro_rata':
      return `${head} ${c.flow} of ${f.n_positions} positions ${verb} pro rata.`
    default:
      return `${head} ${c.flow} of ${f.n_positions} positions ${verb} pro rata, ${f.n_unchanged} untouched.`
  }
}

export default function FlowRow({ f, showFund = true }: { f: FlowEvent; showFund?: boolean }) {
  const c = f.counts
  const selective = c.kept + c.not_added + c.add + c.trim + c.new + c.exit
  return (
    <div className="flow-row" title={`vs. ${fmtDate(f.prev_as_of)}`}>
      <span className="date">{fmtDate(f.as_of)}</span>
      {showFund ? <Link className="fund" to={`/fund/${f.fund}`}>{f.fund}</Link> : <span className="fund">{f.fund}</span>}
      <span>
        <span className={`chip ${f.flow_direction}`}>{f.flow_direction === 'inflow' ? '⇡' : f.flow_direction === 'outflow' ? '⇣' : '·'} {f.flow_direction === 'none' ? 'flows' : f.flow_direction}</span>{' '}
        {flowSentence(f)}
        {selective > 0 && (
          <span>
            {' '}Selective:
            {c.kept > 0 && <> <b>{c.kept} kept</b><Tickers list={f.tickers.kept} /></>}
            {c.not_added > 0 && <> <b>{c.not_added} not added</b><Tickers list={f.tickers.not_added} /></>}
            {c.add > 0 && <> <b>{c.add} added</b><Tickers list={f.tickers.add} /></>}
            {c.trim > 0 && <> <b>{c.trim} trimmed</b><Tickers list={f.tickers.trim} /></>}
            {c.new > 0 && <> <b>{c.new} new</b><Tickers list={f.tickers.new} /></>}
            {c.exit > 0 && <> <b>{c.exit} exited</b><Tickers list={f.tickers.exit} /></>}
          </span>
        )}
        {selective === 0 && f.flow_direction !== 'none' && <span> No selective trades.</span>}
      </span>
    </div>
  )
}
