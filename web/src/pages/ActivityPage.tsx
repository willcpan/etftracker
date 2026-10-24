import { useMemo, useState } from 'react'
import { loadActivity, loadIndex, type Action } from '../api'
import { daysAgoIso } from '../format'
import { Status, useAsync } from '../hooks'
import TradeList from '../components/TradeList'
import ActionLegend from '../components/ActionLegend'

const ACTIONS: Action[] = ['new', 'add', 'trim', 'exit', 'kept', 'not_added']
const LABEL: Record<string, string> = { new: 'new', add: 'add', trim: 'trim', exit: 'exit', kept: 'kept', not_added: 'not added' }

export default function ActivityPage() {
  const act = useAsync(loadActivity, [])
  const idx = useAsync(loadIndex, [])
  const [fund, setFund] = useState('all')
  const [actions, setActions] = useState<Set<Action>>(new Set(ACTIONS))
  const [days, setDays] = useState(90)
  const [minValue, setMinValue] = useState(0)
  const [showFlows, setShowFlows] = useState(true)
  const cutoff = days > 0 ? daysAgoIso(days) : '0000'
  const rows = useMemo(() => {
    if (!act.data) return []
    return act.data.trades.filter((t) =>
      (fund === 'all' || t.fund === fund) && actions.has(t.action) && t.as_of >= cutoff && Math.abs(t.est_value ?? 0) >= minValue,
    )
  }, [act.data, fund, actions, cutoff, minValue])
  const flows = useMemo(() => {
    if (!act.data || !showFlows) return []
    return act.data.flows.filter((f) => (fund === 'all' || f.fund === fund) && f.as_of >= cutoff)
  }, [act.data, fund, cutoff, showFlows])
  if (!act.data) return <Status loading={act.loading} error={act.error} />
  const toggle = (a: Action) => setActions((s) => { const n = new Set(s); if (n.has(a)) n.delete(a); else n.add(a); return n })
  return (
    <div>
      <div className="page-head"><h1>Trading activity</h1><span className="sub">Selective buys, sells, new positions and exits across tracked funds, with the creation/redemption flows they happened against.</span></div>
      <ActionLegend />
      <div className="card">
        <div className="toolbar">
          <label>Fund
            <select value={fund} onChange={(e) => setFund(e.target.value)}>
              <option value="all">All funds</option>
              {idx.data?.funds.map((f) => <option key={f.ticker} value={f.ticker}>{f.ticker}</option>)}
            </select>
          </label>
          <span className="seg" role="group" aria-label="Period">
            {[30, 90, 365, 0].map((d) => <button key={d} className={days === d ? 'active' : ''} onClick={() => setDays(d)}>{d === 0 ? 'All' : `${d}d`}</button>)}
          </span>
          <span className="seg" role="group" aria-label="Actions">
            {ACTIONS.map((a) => <button key={a} className={actions.has(a) ? 'active' : ''} onClick={() => toggle(a)} aria-pressed={actions.has(a)}>{LABEL[a]}</button>)}
          </span>
          <label>Min value
            <select value={minValue} onChange={(e) => setMinValue(Number(e.target.value))}>
              <option value={0}>any</option><option value={1e6}>$1M</option><option value={1e7}>$10M</option><option value={5e7}>$50M</option>
            </select>
          </label>
          <label><input type="checkbox" checked={showFlows} onChange={(e) => setShowFlows(e.target.checked)} /> Show flow days</label>
          <span className="muted small">{rows.length} trades</span>
        </div>
        <TradeList trades={rows} flows={flows} limit={600} />
      </div>
    </div>
  )
}
