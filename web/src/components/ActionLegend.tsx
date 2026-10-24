import type { Action } from '../api'
import { ACTION_HELP } from '../format'
import ActionChip from './ActionChip'

const ORDER: Action[] = ['add', 'trim', 'new', 'exit', 'kept', 'not_added', 'flow']

export default function ActionLegend() {
  return (
    <details className="card" style={{ padding: '10px 16px', marginBottom: 16 }}>
      <summary style={{ cursor: 'pointer', fontWeight: 600 }}>How to read these labels</summary>
      <p className="small" style={{ margin: '8px 0 10px' }}>
        ETF share counts move for two reasons: the manager trades, or investors create/redeem ETF shares and every
        position scales pro rata. The fund's creation/redemption <b>flow</b> is measured first (from ETF shares
        outstanding when the file reports it), and each position is then judged against it.
      </p>
      <div className="legend-box">
        {ORDER.map((a) => (
          <div key={a}><ActionChip action={a} /> {ACTION_HELP[a]}</div>
        ))}
      </div>
    </details>
  )
}
