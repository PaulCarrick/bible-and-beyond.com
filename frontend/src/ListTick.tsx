import { useContext } from 'react'
import { AccountContext } from './AccountContext'
import type { ListItem } from './listItems'
import type { ListPicks } from './listPicks'

interface ListTickProps {
  item: ListItem
  picks: ListPicks
}

// The checkbox at the right of a search result that ticks it for a list (My lists; the owner's request, 2026-11-17,
// "like playlists"). Shown only to a logged-in member.
function ListTick({ item, picks }: ListTickProps) {
  const { user } = useContext(AccountContext)
  if (!user) {
    return null
  }
  return (
    <input
      type="checkbox"
      className="list-tick"
      checked={picks.isPicked(item.key)}
      onChange={(event) => picks.toggle(item, event.target.checked)}
      aria-label={`Save ${item.title}${item.source ? ` (${item.source})` : ''} in a list`}
      title="Tick to save this in a list"
    />
  )
}

export default ListTick
