export const pct = (x: number | null | undefined, digits = 2): string =>
  x == null ? '—' : `${(x * 100).toFixed(digits)}%`

export const pp = (x: number | null | undefined, digits = 2): string => {
  if (x == null) return '—'
  const v = x * 100
  return `${v > 0 ? '+' : ''}${v.toFixed(digits)} pp`
}

export const signedPct = (x: number | null | undefined, digits = 1): string =>
  x == null ? '—' : `${x > 0 ? '+' : ''}${(x * 100).toFixed(digits)}%`

export const money = (x: number | null | undefined, compact = true): string => {
  if (x == null) return '—'
  const abs = Math.abs(x)
  if (compact) {
    if (abs >= 1e9) return `${x < 0 ? '-' : ''}$${(abs / 1e9).toFixed(2)}B`
    if (abs >= 1e6) return `${x < 0 ? '-' : ''}$${(abs / 1e6).toFixed(1)}M`
    if (abs >= 1e3) return `${x < 0 ? '-' : ''}$${(abs / 1e3).toFixed(0)}K`
  }
  return `${x < 0 ? '-' : ''}$${abs.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

export const signedMoney = (x: number | null | undefined): string =>
  x == null ? '—' : `${x > 0 ? '+' : ''}${money(x)}`

export const int = (x: number | null | undefined): string =>
  x == null ? '—' : Math.round(x).toLocaleString()

export const signedInt = (x: number | null | undefined): string =>
  x == null ? '—' : `${x > 0 ? '+' : ''}${Math.round(x).toLocaleString()}`

export const num = (x: number | null | undefined, digits = 2): string =>
  x == null ? '—' : x.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })

export const fmtDate = (iso: string | null | undefined): string => {
  if (!iso) return '—'
  const d = new Date(iso + (iso.length === 10 ? 'T00:00:00' : ''))
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export const shortDate = (iso: string): string => {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export const fmtDateTime = (iso: string | null | undefined): string =>
  iso ? new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—'

export const daysAgoIso = (days: number): string => {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return d.toISOString().slice(0, 10)
}

export const ACTION_LABEL: Record<string, string> = {
  new: 'New position',
  exit: 'Exited',
  add: 'Added',
  trim: 'Trimmed',
  kept: 'Kept through outflow',
  not_added: 'Not added on inflow',
  flow: 'Scaled with flows',
  hold: 'No change',
}

export const ACTION_SHORT: Record<string, string> = {
  new: 'new', exit: 'exit', add: 'add', trim: 'trim', kept: 'kept', not_added: 'not added', flow: 'flow', hold: 'hold',
}

export const ACTION_ICON: Record<string, string> = {
  new: '✚', exit: '✕', add: '▲', trim: '▼', kept: '◆', not_added: '◇', flow: '≈', hold: '·',
}

export const ACTION_HELP: Record<string, string> = {
  new: 'Position appears for the first time.',
  exit: 'Position is gone.',
  add: 'Share count grew by more than creations explain: an active buy.',
  trim: 'Share count fell by more than redemptions explain: an active sell.',
  kept: 'Fund had an outflow and scaled most positions down pro rata, but this one was left untouched: the manager chose to keep it.',
  not_added: 'Fund had an inflow and scaled most positions up pro rata, but this one was not bought: the manager chose not to add.',
  flow: 'Share count moved in step with creations/redemptions. Not a trading decision.',
  hold: 'No change on a day without meaningful flows.',
}

export const flowLabel = (dir: string | null | undefined, pct: number | null | undefined): string =>
  dir === 'inflow' ? `${signedPct(pct, 2)} inflow` : dir === 'outflow' ? `${signedPct(pct, 2)} outflow` : 'no meaningful flow'

/** Read a CSS custom property from :root (for chart libraries that need literal colors). */
export function cssVar(name: string): string {
  if (typeof window === 'undefined') return '#888'
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#888'
}

export const SERIES = ['--series-1', '--series-2', '--series-3', '--series-4', '--series-5', '--series-6', '--series-7', '--series-8']
