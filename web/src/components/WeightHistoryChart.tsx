import { useMemo } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { History } from '../api'
import { SERIES, cssVar, fmtDate, pct, shortDate } from '../format'
import { useTheme } from '../App'

interface Props {
  history: History
  selected: string[] // security keys, max 8
  mode?: 'weight' | 'shares'
}

interface Pt { date: string; [k: string]: number | string | null }

function TooltipBox({ active, payload, label, mode }: { active?: boolean; payload?: { name: string; value: number | null; color: string }[]; label?: string; mode: 'weight' | 'shares' }) {
  if (!active || !payload?.length) return null
  const rows = [...payload].filter((p) => p.value != null).sort((a, b) => (b.value ?? 0) - (a.value ?? 0))
  return (
    <div className="tooltip">
      <div className="t">{fmtDate(label)}</div>
      {rows.map((p) => (
        <div className="row" key={p.name}>
          <span><i className="legend-dot" style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 2, background: p.color, marginRight: 6 }} />{p.name}</span>
          <span className="num">{mode === 'weight' ? pct(p.value) : Math.round(p.value ?? 0).toLocaleString()}</span>
        </div>
      ))}
    </div>
  )
}

export default function WeightHistoryChart({ history, selected, mode = 'weight' }: Props) {
  const { resolved } = useTheme()
  const colors = useMemo(() => SERIES.map(cssVar), [resolved]) // eslint-disable-line react-hooks/exhaustive-deps
  const grid = cssVar('--grid')
  const axis = cssVar('--muted')
  const idx = useMemo(() => new Map(history.securities.map((s, i) => [s.key, i])), [history])
  const series = selected.slice(0, 8).map((k) => ({ key: k, i: idx.get(k) }))
    .filter((s): s is { key: string; i: number } => s.i != null)
  const data: Pt[] = useMemo(
    () =>
      history.dates.map((d, j) => {
        const pt: Pt = { date: d }
        for (const s of series) pt[s.key] = (mode === 'weight' ? history.weights : history.shares)[s.i][j]
        return pt
      }),
    [history, mode, selected.join('|')], // eslint-disable-line react-hooks/exhaustive-deps
  )
  if (!series.length) return <div className="empty">Select at least one holding to chart.</div>
  const label = (k: string) => {
    const s = history.securities[idx.get(k)!]
    return s.ticker ?? s.name
  }
  return (
    <div>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={grid} vertical={false} />
          <XAxis dataKey="date" tickFormatter={shortDate} stroke={axis} tick={{ fill: axis, fontSize: 12 }} tickLine={false} axisLine={{ stroke: cssVar('--axis') }} minTickGap={32} />
          <YAxis
            stroke={axis}
            tick={{ fill: axis, fontSize: 12 }}
            tickLine={false}
            axisLine={false}
            width={56}
            tickFormatter={(v: number) => (mode === 'weight' ? `${(v * 100).toFixed(1)}%` : v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(0)}K` : String(v))}
            domain={mode === 'weight' ? [0, 'auto'] : ['auto', 'auto']}
          />
          <Tooltip content={<TooltipBox mode={mode} />} cursor={{ stroke: axis, strokeDasharray: '3 3' }} />
          {series.map((s, n) => (
            <Line key={s.key} type="monotone" dataKey={s.key} name={label(s.key)} stroke={colors[n]} strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: cssVar('--surface') }} connectNulls={false} isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <div className="legend" role="list">
        {series.map((s, n) => (
          <span role="listitem" key={s.key}><i style={{ background: colors[n] }} />{label(s.key)}</span>
        ))}
      </div>
    </div>
  )
}
