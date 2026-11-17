import { useContext, useEffect, useState } from 'react'
import { AccountContext } from './AccountContext'
import { fetchLists, saveToList } from './api'
import type { SavedListSummary } from './api'
import type { ListPicks } from './listPicks'

interface ListSaveBoxProps {
  picks: ListPicks
}

const NEW_LIST = 'new'

// Under a search's results, once something is ticked (My lists; the owner's request, 2026-11-17): save the ticked
// results as a new list with a name, or add them to one of the member's lists; Cancel clears the ticks. The search
// pages are forms, so Enter here saves the list rather than searching. A plain container, not a form.
function ListSaveBox({ picks }: ListSaveBoxProps) {
  const { user, onNavigate } = useContext(AccountContext)
  const [lists, setLists] = useState<SavedListSummary[] | null>(null)
  const [choice, setChoice] = useState(NEW_LIST)
  const [name, setName] = useState('')
  const [isBusy, setIsBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const count = picks.picks.length
  const hasPicks = count > 0 && user !== null

  // The member's lists, once the box is first shown (to offer adding to one).
  useEffect(() => {
    if (!hasPicks || lists !== null) {
      return
    }
    fetchLists()
      .then(setLists)
      .catch(() => setLists([]))
  }, [hasPicks, lists])

  if (!user || (!hasPicks && !message && !errorMessage)) {
    return null
  }

  const trimmedName = name.trim().replace(/\s+/g, ' ')
  const canSave = choice !== NEW_LIST || trimmedName !== ''

  async function handleSave() {
    if (!canSave || isBusy) {
      return
    }
    setIsBusy(true)
    setMessage('')
    setErrorMessage('')
    try {
      const { list, added } = await saveToList(picks.picks, choice === NEW_LIST ? { name: trimmedName } : { listId: Number(choice) })
      setLists((current) => [list, ...(current ?? []).filter((each) => each.id !== list.id)])
      const already = count - added
      setMessage(
        `Saved ${added} ${added === 1 ? 'entry' : 'entries'} in “${list.name}” (${list.count} in all)` +
          (already > 0 ? `; ${already} ${already === 1 ? 'was' : 'were'} in it already.` : '.'),
      )
      picks.clear()
      setName('')
      setChoice(String(list.id))
    } catch (error) {
      setErrorMessage((error as Error).message)
    } finally {
      setIsBusy(false)
    }
  }

  return (
    <div className="list-save" role="group" aria-label="Save the ticked results in a list">
      {hasPicks && (
        <div className="list-save-row">
          <p className="list-save-count">
            {count} ticked to save in a list.
          </p>
          <label>
            Save in{' '}
            <select value={choice} onChange={(event) => setChoice(event.target.value)}>
              <option value={NEW_LIST}>A new list</option>
              {(lists ?? []).map((list) => (
                <option key={list.id} value={list.id}>
                  {list.name} ({list.count})
                </option>
              ))}
            </select>
          </label>
          {choice === NEW_LIST && (
            <label>
              List name{' '}
              <input
                type="text"
                value={name}
                maxLength={100}
                placeholder="Such as Comfort verses"
                onChange={(event) => setName(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    handleSave()
                  }
                }}
              />
            </label>
          )}
          <button type="button" className="primary-button" disabled={!canSave || isBusy} onClick={handleSave}>
            {isBusy ? 'Saving…' : 'Save'}
          </button>
          <button
            type="button"
            className="secondary-button"
            disabled={isBusy}
            onClick={() => {
              picks.clear()
              setMessage('')
              setErrorMessage('')
            }}
          >
            Cancel
          </button>
        </div>
      )}
      {message && (
        <p role="status" className="list-save-message">
          {message}{' '}
          <button type="button" className="link-button" onClick={() => onNavigate('lists')}>
            Open My lists
          </button>
        </p>
      )}
      {errorMessage && (
        <p className="error" role="alert">
          {errorMessage}
        </p>
      )}
    </div>
  )
}

export default ListSaveBox
