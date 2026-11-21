import { useCallback, useContext, useEffect, useRef, useState } from 'react'
import { AccountContext } from './AccountContext'
import { copyListToNote, deleteList, exportLists, fetchList, fetchLists, importLists, removeListEntry, renameList, shareList } from './api'
import type { SavedList, SavedListEntry, SavedListSummary } from './api'
import { openWords } from './listWords'
import type { View } from './views'

interface MyListsPageProps {
  // Opens an entry where it came from (the Bible reader, a commentary, a reading, a song, a map, an FAQ answer).
  onOpenEntry: (entry: SavedListEntry) => void
  onNavigate: (view: View) => void
}


// My lists (the "My lists" link beside My notes; the owner's request, 2026-11-17): the member's lists of search
// results, each entry as its search showed it (kept, not searched again), with a link that opens it, Remove, a
// search in the list, Rename, Delete, and Copy to notes (one note holding the whole list, on its first verse).
// Export (all lists, or the one shown) saves a JSON file that Import reads back, here or on another copy of the
// site; Share puts a list on Public lists, for accounts an administrator allowed (share_lists; 2026-11-19).
function MyListsPage({ onOpenEntry, onNavigate }: MyListsPageProps) {
  const { user } = useContext(AccountContext)
  const importInput = useRef<HTMLInputElement>(null)
  const [lists, setLists] = useState<SavedListSummary[] | null>(null)
  const [chosen, setChosen] = useState<SavedList | null>(null)
  const [filter, setFilter] = useState('')
  const [renaming, setRenaming] = useState<string | null>(null)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [message, setMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [isBusy, setIsBusy] = useState(false)

  const open = useCallback(async (id: number) => {
    setErrorMessage('')
    setMessage('')
    setRenaming(null)
    setConfirmingDelete(false)
    setFilter('')
    try {
      setChosen(await fetchList(id))
    } catch (error) {
      setErrorMessage((error as Error).message)
    }
  }, [])

  // The lists when the page opens; the most recently changed one is shown.
  useEffect(() => {
    let isCurrent = true
    fetchLists()
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

  async function act(work: () => Promise<void>) {
    setIsBusy(true)
    setErrorMessage('')
    setMessage('')
    try {
      await work()
    } catch (error) {
      setErrorMessage((error as Error).message)
    } finally {
      setIsBusy(false)
    }
  }

  function remember(list: SavedList) {
    setChosen(list)
    setLists((current) =>
      (current ?? []).map((each) => (each.id === list.id ? { ...each, name: list.name, count: list.count, shared: list.shared } : each)),
    )
  }

  // Import: the chosen file becomes new lists; the first of them is shown.
  function importFile(file: File) {
    act(async () => {
      const result = await importLists(file)
      setLists(await fetchLists())
      const names = (items: { name: string }[]) => items.map((each) => `“${each.name}”`).join(', ')
      const parts = []
      if (result.lists.length > 0) {
        parts.push(`${result.lists.length} ${result.lists.length === 1 ? 'list' : 'lists'}: ${names(result.lists)}`)
      }
      if (result.playlists.length > 0) {
        parts.push(`${result.playlists.length} ${result.playlists.length === 1 ? 'playlist' : 'playlists'} (on the Christian media page): ${names(result.playlists)}`)
      }
      const left = result.skipped > 0 ? ` ${result.skipped} ${result.skipped === 1 ? 'entry' : 'entries'} could not be kept here and were left out.` : ''
      const leftSongs =
        result.skipped_songs > 0 ? ` ${result.skipped_songs} ${result.skipped_songs === 1 ? 'song was not on this site and was' : 'songs were not on this site and were'} left out.` : ''
      setMessage(`${parts.length > 0 ? `Imported ${parts.join('; and ')}.` : 'Nothing could be imported.'}${left}${leftSongs}`)
      if (result.lists.length > 0) {
        setChosen(result.lists[0])
      }
    })
  }

  const words = filter.trim().toLowerCase().split(/\s+/).filter(Boolean)
  const shownEntries = (chosen?.items ?? []).filter((entry) =>
    words.every((word) => `${entry.title} ${entry.source} ${entry.text}`.toLowerCase().includes(word)),
  )

  return (
    <div className="my-lists-page">
      <h1>My lists</h1>
      <p>
        Results you ticked in the searches and saved, kept as the search showed them. Tick results in any search and
        use <em>Save</em> under them to make a list or add to one.
      </p>
      {errorMessage && (
        <p className="error" role="alert">
          {errorMessage}
        </p>
      )}
      {message && (
        <p role="status" className="list-save-message">
          {message}{' '}
          {message.includes('is now on Public lists') && (
            <button type="button" className="link-button" onClick={() => onNavigate('publicLists')}>
              Open Public lists
            </button>
          )}
          {message.startsWith('Copied') && (
            <button type="button" className="link-button" onClick={() => onNavigate('notes')}>
              Open My notes
            </button>
          )}
        </p>
      )}
      <div className="my-list-actions">
        <button
          type="button"
          className="secondary-button"
          disabled={isBusy || !lists}
          onClick={() => act(() => exportLists())}
        >
          Export all lists and playlists
        </button>
        <button type="button" className="secondary-button" disabled={isBusy} onClick={() => importInput.current?.click()}>
          Import lists and playlists…
        </button>
        <input
          ref={importInput}
          type="file"
          accept=".json,application/json"
          hidden
          onChange={(event) => {
            const file = event.target.files?.[0]
            event.target.value = ''
            if (file) {
              importFile(file)
            }
          }}
        />
      </div>
      {lists === null && !errorMessage && <p>Loading…</p>}
      {lists !== null && lists.length === 0 && <p>You have no lists yet.</p>}
      {lists !== null && lists.length > 0 && (
        <ul className="my-lists-index" aria-label="Your lists">
          {lists.map((list) => (
            <li key={list.id}>
              <button
                type="button"
                className={chosen?.id === list.id ? 'secondary-button is-chosen' : 'secondary-button'}
                aria-current={chosen?.id === list.id ? 'true' : undefined}
                onClick={() => open(list.id)}
              >
                {list.name} ({list.count}){list.shared ? ' · shared' : ''}
              </button>
            </li>
          ))}
        </ul>
      )}

      {chosen && (
        <section aria-labelledby="my-list-heading">
          {renaming === null ? (
            <h2 id="my-list-heading">{chosen.name}</h2>
          ) : (
            <div className="my-list-actions">
              <label>
                New name{' '}
                <input
                  type="text"
                  value={renaming}
                  maxLength={100}
                  onChange={(event) => setRenaming(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && renaming.trim()) {
                      act(async () => {
                        remember(await renameList(chosen.id, renaming))
                        setRenaming(null)
                      })
                    }
                  }}
                />
              </label>
              <button
                type="button"
                className="primary-button"
                disabled={isBusy || !renaming.trim()}
                onClick={() =>
                  act(async () => {
                    remember(await renameList(chosen.id, renaming))
                    setRenaming(null)
                  })
                }
              >
                Save the name
              </button>
              <button type="button" className="secondary-button" onClick={() => setRenaming(null)}>
                Cancel
              </button>
            </div>
          )}
          <div className="my-list-actions">
            <button
              type="button"
              className="secondary-button"
              disabled={isBusy || chosen.items.length === 0}
              onClick={() =>
                act(async () => {
                  const note = await copyListToNote(chosen.id)
                  setMessage(`Copied the list into a note on ${note.title}.`)
                })
              }
            >
              Copy to notes
            </button>
            {renaming === null && (
              <button type="button" className="secondary-button" onClick={() => setRenaming(chosen.name)}>
                Rename
              </button>
            )}
            <button type="button" className="secondary-button" disabled={isBusy} onClick={() => act(() => exportLists(chosen.id))}>
              Export this list
            </button>
            {/* Sharing is for accounts an administrator allowed; a shared list can always be unshared. */}
            {(user?.share_lists || chosen.shared) && (
              <button
                type="button"
                className="secondary-button"
                disabled={isBusy}
                onClick={() =>
                  act(async () => {
                    const changed = await shareList(chosen.id, !chosen.shared)
                    remember(changed)
                    setMessage(changed.shared ? `“${changed.name}” is now on Public lists, for everyone to see.` : `“${changed.name}” is no longer shared.`)
                  })
                }
              >
                {chosen.shared ? 'Stop sharing' : 'Share on Public lists'}
              </button>
            )}
            {confirmingDelete ? (
              <>
                <span>Delete “{chosen.name}”?</span>
                <button
                  type="button"
                  className="secondary-button danger-button"
                  disabled={isBusy}
                  onClick={() =>
                    act(async () => {
                      await deleteList(chosen.id)
                      const left = (lists ?? []).filter((each) => each.id !== chosen.id)
                      setLists(left)
                      setChosen(null)
                      setConfirmingDelete(false)
                      setMessage(`Deleted the list “${chosen.name}”.`)
                      if (left.length > 0) {
                        await open(left[0].id)
                      }
                    })
                  }
                >
                  Yes, delete it
                </button>
                <button type="button" className="secondary-button" onClick={() => setConfirmingDelete(false)}>
                  Cancel
                </button>
              </>
            ) : (
              <button type="button" className="secondary-button" onClick={() => setConfirmingDelete(true)}>
                Delete the list
              </button>
            )}
          </div>
          {chosen.items.length > 5 && (
            <label className="my-list-filter">
              Find in this list{' '}
              <input type="search" value={filter} onChange={(event) => setFilter(event.target.value)} />
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
                {/* As the searches show them: a reading or chapter after its book, a verse or note before its source. */}
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
                  <button
                    type="button"
                    className="link-button context-link"
                    disabled={isBusy}
                    onClick={() => act(async () => remember(await removeListEntry(chosen.id, entry.id)))}
                  >
                    Remove from the list
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

export default MyListsPage
