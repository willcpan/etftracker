import type { Action } from '../api'
import { ACTION_HELP, ACTION_ICON, ACTION_LABEL, ACTION_SHORT } from '../format'

export default function ActionChip({ action, short = false, showHold = false }: { action: Action | null | undefined; short?: boolean; showHold?: boolean }) {
  if (!action || (action === 'hold' && !showHold)) return null
  return (
    <span className={`chip ${action}`} title={`${ACTION_LABEL[action]}. ${ACTION_HELP[action]}`}>
      <span aria-hidden="true">{ACTION_ICON[action]}</span>
      {short ? ACTION_SHORT[action] : ACTION_LABEL[action]}
    </span>
  )
}
