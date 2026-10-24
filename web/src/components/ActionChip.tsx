import type { Action } from '../api'
import { ACTION_ICON, ACTION_LABEL } from '../format'

export default function ActionChip({ action, short = false }: { action: Action | null | undefined; short?: boolean }) {
  if (!action || action === 'hold') return null
  return (
    <span className={`chip ${action}`} title={ACTION_LABEL[action]}>
      <span aria-hidden="true">{ACTION_ICON[action]}</span>
      {short ? action : ACTION_LABEL[action]}
    </span>
  )
}
