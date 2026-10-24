export type Action = 'new' | 'exit' | 'add' | 'trim' | 'hold'

export interface FundMeta {
  ticker: string
  name: string
  manager: string
  website: string | null
  exchange: string | null
  inception: string | null
}

export interface ChangeCounts { new: number; exit: number; add: number; trim: number }

export interface FundSummary extends FundMeta {
  latest_as_of: string
  prev_as_of: string | null
  first_as_of: string
  n_snapshots: number
  n_positions: number
  net_assets: number | null
  cash_weight: number | null
  latest_changes: ChangeCounts
  top_holdings: { ticker: string | null; name: string; weight: number | null }[]
}

export interface Trade {
  fund: string
  as_of: string
  prev_as_of: string
  key: string
  ticker: string | null
  name: string
  shares_prev: number | null
  shares_now: number | null
  shares_change: number | null
  adj_change: number | null
  weight_prev: number | null
  weight_now: number | null
  weight_change: number | null
  est_value: number | null
  flow_factor: number | null
  basis: 'shares' | 'weight'
  action: Action
}

export interface IndexFile {
  generated_at: string
  funds: FundSummary[]
  recent_activity: Trade[]
  n_securities: number
}

export interface HoldingChange {
  shares_change: number | null
  adj_change: number | null
  weight_change: number | null
  est_value: number | null
  weight_prev: number | null
  action: Action
}

export interface Holding {
  key: string
  ticker: string | null
  name: string
  cusip: string | null
  asset_type: 'equity' | 'cash' | 'other'
  shares: number | null
  price: number | null
  market_value: number | null
  weight: number | null
  change?: HoldingChange
}

export interface History {
  dates: string[]
  securities: { key: string; ticker: string | null; name: string }[]
  weights: (number | null)[][]
  shares: (number | null)[][]
  cash_weight: (number | null)[]
  n_positions: number[]
  net_assets: (number | null)[]
}

export interface FundDetail {
  fund: FundMeta
  generated_at: string
  latest_as_of: string
  prev_as_of: string | null
  fetched_at: string | null
  source_url: string | null
  n_snapshots: number
  n_positions: number
  net_assets: number | null
  cash_weight: number | null
  flow_factor: number | null
  latest_changes: ChangeCounts
  trade_threshold: number
  holdings: Holding[]
  history: History
  trades: Trade[]
  diffs: { as_of: string; prev_as_of: string; flow_factor: number; n_prev: number; n_now: number; counts: ChangeCounts }[]
}

export interface SecurityEntry {
  key: string
  ticker: string | null
  name: string
  funds: { fund: string; weight: number; shares: number | null; market_value: number | null; as_of: string; action: Action | null }[]
}

const cache = new Map<string, Promise<unknown>>()

export function dataUrl(path: string): string {
  const base = import.meta.env.BASE_URL.endsWith('/') ? import.meta.env.BASE_URL : import.meta.env.BASE_URL + '/'
  return `${base}data/${path}`
}

export function loadJson<T>(path: string): Promise<T> {
  if (!cache.has(path)) {
    cache.set(
      path,
      fetch(dataUrl(path)).then((r) => {
        if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`)
        return r.json()
      }),
    )
  }
  return cache.get(path) as Promise<T>
}

export const loadIndex = () => loadJson<IndexFile>('index.json')
export const loadFund = (ticker: string) => loadJson<FundDetail>(`funds/${ticker}.json`)
export const loadActivity = () => loadJson<{ trades: Trade[] }>('activity.json')
export const loadSecurities = () => loadJson<{ securities: SecurityEntry[] }>('securities.json')
