import { useContext, useState } from 'react'
import { AccountContext } from './AccountContext'
import type { ListItem } from './listItems'
import { SELECT_ALL_LIMIT } from './listPicks'
import type { ListPicks } from './listPicks'

interface ListSelectAllProps {
  picks: ListPicks
  // How many results the search found in all (on every page, shown or not).
  total: number
  // Names the search shown, so a new search starts unticked.
  searchKey: string
  // Every result of the search, up to the limit, fetched page by page from the server.
  fetchAll: (limit: number) => Promise<ListItem[]>
  // The music search ticks the same songs for a playlist too.
  onChange?: (items: ListItem[], isTicked: boolean) => void
}

// "Select all" above a search's checkboxes (the owner's request, 2026-11-17): ticks every result of the search,
// on every page and behind every "Show more", not only those shown; unticking it unticks them again. A search
// with more results than one save takes ticks the first 200.
function ListSelectAll({ picks, total, searchKey, fetchAll, onChange }: ListSelectAllProps) {
  const { user } = useContext(AccountContext)
  const [selected, setSelected] = useState<{ searchKey: string; items: ListItem[] } | null>(null)
  const [isBusy, setIsBusy] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  if (!user || total === 0) {
    return null
  }
  const items = selected?.searchKey === searchKey ? selected.items : []
  const isChecked = items.length > 0 && items.every((item) => picks.isPicked(item.key))
  const count = Math.min(total, SELECT_ALL_LIMIT)

  async function handleChange(isTicked: boolean) {
    setErrorMessage('')
    if (!isTicked) {
      picks.removeMany(items.map((item) => item.key))
      onChange?.(items, false)
      return
    }
    setIsBusy(true)
    try {
      const found = (await fetchAll(SELECT_ALL_LIMIT)).slice(0, SELECT_ALL_LIMIT)
      setSelected({ searchKey, items: found })
      picks.addMany(found)
      onChange?.(found, true)
    } catch (error) {
      setErrorMessage((error as Error).message || 'The results could not be fetched.')
    } finally {
      setIsBusy(false)
    }
  }

  return (
    <div className="list-select-all">
      {errorMessage && (
        <span className="error" role="alert">
          {errorMessage}
        </span>
      )}
      <label>
        {isBusy ? 'Ticking…' : total > SELECT_ALL_LIMIT ? `Select the first ${count} of ${total.toLocaleString()}` : `Select all ${count}`}
        <input
          type="checkbox"
          className="list-select-all-tick"
          checked={isChecked}
          disabled={isBusy}
          onChange={(event) => handleChange(event.target.checked)}
          title="Tick every result of this search for a list, on every page"
        />
      </label>
    </div>
  )
}

export default ListSelectAll

