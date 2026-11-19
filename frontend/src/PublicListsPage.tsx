import { useCallback, useContext, useEffect, useState } from 'react'
import { AccountContext } from './AccountContext'
import { copyPublicList, fetchPublicList, fetchPublicLists } from './api'
import type { SavedList, SavedListEntry, SavedListSummary } from './api'
import { openWords } from './listWords'
import type { View } from './views'

interface PublicListsPageProps {
  // Opens an entry where it came from, as on My lists.
  onOpenEntry: (entry: SavedListEntry) => void
  onNavigate: (view: View) => void
}

// Public lists (under Members; the owner's request, 2026-11-19): the lists members shared from My lists (accounts an
// administrator allowed to share), for everyone who can use the site. Each shows who shared it and its entries,
// which open where they came from; a logged-in member can copy one into their own lists.
function PublicListsPage({ onOpenEntry, onNavigate }: PublicListsPageProps) {
  const { user } = useContext(AccountContext)
  const [lists, setLists] = useState<SavedListSummary[] | null>(null)
  const [chosen, setChosen] = useState<SavedList | null>(null)
  const [filter, setFilter] = useState('')
  const [message, setMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [isBusy, setIsBusy] = useState(false)

  const open = useCallback(async (id: number) => {
    setErrorMessage('')
    setMessage('')
    setFilter('')
    try {
      setChosen(await fetchPublicList(id))
    } catch (error) {
      setErrorMessage((error as Error).message)
    }
  }, [])

  useEffect(() => {
    let isCurrent = true
    fetchPublicLists()
      .then((found) => {
        if (!isCurrent) {
          return
        }
        setLists(found)
        if (found.length > 0) {
          open(found[0].id)
        }
      })
      .catch((error: Error) => isCurrent && setErrorMessage(error.message))
    return () => {
      isCurrent = false
    }
  }, [open])

  async function copy(list: SavedList) {
    setIsBusy(true)
    setErrorMessage('')
    setMessage('')
    try {
      const copied = await copyPublicList(list.id)
      setMessage(`Copied into My lists as “${copied.name}”.`)
    } catch (error) {
      setErrorMessage((error as Error).message)
    } finally {
      setIsBusy(false)
    }
  }

  const words = filter.trim().toLowerCase().split(/\s+/).filter(Boolean)
  const shownEntries = (chosen?.items ?? []).filter((entry) =>
    words.every((word) => `${entry.title} ${entry.source} ${entry.text}`.toLowerCase().includes(word)),
  )

  return (
    <div className="my-lists-page">
      <h1>Public lists</h1>
      <p>Lists of verses, readings, songs and more that members chose to share with everyone.</p>
      {errorMessage && (
        <p className="error" role="alert">
          {errorMessage}
        </p>
      )}
      {message && (
        <p role="status" className="list-save-message">
          {message}{' '}
          <button type="button" className="link-button" onClick={() => onNavigate('lists')}>
            Open My lists
          </button>
        </p>
      )}
      {lists === null && !errorMessage && <p>Loading…</p>}
      {lists !== null && lists.length === 0 && <p>No lists have been shared yet.</p>}
      {lists !== null && lists.length > 0 && (
        <ul className="my-lists-index" aria-label="Shared lists">
          {lists.map((list) => (
            <li key={list.id}>
              <button
                type="button"
                className={chosen?.id === list.id ? 'secondary-button is-chosen' : 'secondary-button'}
                aria-current={chosen?.id === list.id ? 'true' : undefined}
                onClick={() => open(list.id)}
              >
                {list.name} ({list.count}) · {list.owner}
              </button>
            </li>
          ))}
        </ul>
      )}
      {chosen && (
        <section aria-labelledby="public-list-heading">
          <h2 id="public-list-heading">{chosen.name}</h2>
          <p className="public-list-owner">Shared by {chosen.owner}</p>
          {user && (
            <div className="my-list-actions">
              <button type="button" className="secondary-button" disabled={isBusy || chosen.items.length === 0} onClick={() => copy(chosen)}>
                Copy to My lists
              </button>
            </div>
          )}
          {chosen.items.length > 5 && (
            <label className="my-list-filter">
              Find in this list <input type="search" value={filter} onChange={(event) => setFilter(event.target.value)} />
            </label>
          )}
          <p>
            {words.length > 0
              ? `${shownEntries.length} of ${chosen.items.length} ${chosen.items.length === 1 ? 'entry' : 'entries'}`
              : `${chosen.items.length} ${chosen.items.length === 1 ? 'entry' : 'entries'}`}
          </p>
          <ul className="result-list book-results">
            {shownEntries.map((entry) => (
              <li key={entry.id} className="result book-result my-list-entry">
                <div className="book-result-place">
                  {(entry.kind === 'devotional' || entry.kind === 'book') && entry.source && entry.source !== entry.title ? (
                    <>
                      <strong>{entry.source}</strong> · {entry.title}
                    </>
                  ) : (
                    <>
                      <strong>{entry.title}</strong>
                      {entry.source && <span className="book-result-source"> · {entry.source}</span>}
                    </>
                  )}
                </div>
                {entry.text && <p className="book-result-text">{entry.text}</p>}
                <div className="verse-links">
                  <button type="button" className="link-button context-link" onClick={() => onOpenEntry(entry)}>
                    {openWords[entry.kind]}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

export default PublicListsPage
