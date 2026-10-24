import { useEffect, useState } from 'react'

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): { data: T | null; error: string | null; loading: boolean } {
  const [state, setState] = useState<{ data: T | null; error: string | null; loading: boolean }>({ data: null, error: null, loading: true })
  useEffect(() => {
    let alive = true
    setState((s) => ({ ...s, loading: true, error: null }))
    fn().then(
      (data) => alive && setState({ data, error: null, loading: false }),
      (e) => alive && setState({ data: null, error: String(e?.message ?? e), loading: false }),
    )
    return () => { alive = false }
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps
  return state
}

export function Status({ loading, error }: { loading: boolean; error: string | null }) {
  if (error) return <div className="empty">Could not load data: {error}. If this is a fresh deployment, the daily job may not have run yet.</div>
  if (loading) return <div className="empty">Loading…</div>
  return null
}
