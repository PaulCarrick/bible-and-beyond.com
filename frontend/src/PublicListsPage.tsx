import { useCallback, useContext, useEffect, useState } from 'react'
import { AccountContext } from './AccountContext'
import { copyPublicList, copyPublicPlaylist, fetchPublicList, fetchPublicLists, fetchPublicPlaylist, fetchPublicPlaylists, sharedPlaylistAddress } from './api'
import type { Playlist, PublicPlaylist, SavedList, SavedListEntry, SavedListSummary } from './api'
import { openWords } from './listWords'
import type { View } from './views'

interface PublicListsPageProps {
  // Opens an entry where it came from, as on My lists.
  onOpenEntry: (entry: SavedListEntry) => void
  onNavigate: (view: View) => void
  // Plays a shared playlist on the music page.
  onPlayPlaylist: (name: string, songIds: string[]) => void
  // A shared playlist to open first (from a /public-lists?playlist=12 link).
  initialPlaylistId: number | null
}

// What is shown: one shared list, or one shared playlist.
type Chosen = { kind: 'list'; list: SavedList } | { kind: 'playlist'; playlist: PublicPlaylist }

// One button of the index: a shared list or a shared playlist, most recently changed first.
type IndexEntry = { kind: 'list'; summary: SavedListSummary } | { kind: 'playlist'; summary: Playlist }

// Public lists (under Members; the owner's request, 2026-11-19): the lists members shared from My lists (accounts an
// administrator allowed to share), for everyone who can use the site. Each shows who shared it and its entries,
// which open where they came from; a logged-in member can copy one into their own lists. Shared playlists (2026-11-21,
// the owner's request) are in the same index, marked "Playlist": Play plays one on the music page, each song opens on
// it, and a logged-in visitor can copy one into their own playlists. A link to one (/public-lists?playlist=12) opens it.
function PublicListsPage({ onOpenEntry, onNavigate, onPlayPlaylist, initialPlaylistId }: PublicListsPageProps) {
  const { user } = useContext(AccountContext)
  const [index, setIndex] = useState<IndexEntry[] | null>(null)
  const [chosen, setChosen] = useState<Chosen | null>(null)
  const [filter, setFilter] = useState('')
  const [message, setMessage] = useState('')
  // Where the button after the message goes: My lists, or the music page for a copied playlist.
  const [messageView, setMessageView] = useState<View | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [isBusy, setIsBusy] = useState(false)

  const open = useCallback(async (kind: 'list' | 'playlist', id: number) => {
    setErrorMessage('')
    setMessage('')
    setFilter('')
    try {
      setChosen(kind === 'list' ? { kind, list: await fetchPublicList(id) } : { kind, playlist: await fetchPublicPlaylist(id) })
    } catch (error) {
      setErrorMessage((error as Error).message)
    }
  }, [])

  useEffect(() => {
    let isCurrent = true
    Promise.all([fetchPublicLists(), fetchPublicPlaylists()])
      .then(([lists, playlists]) => {
        if (!isCurrent) {
          return
        }
        const entries: IndexEntry[] = [
          ...lists.map((summary) => ({ kind: 'list' as const, summary })),
          ...playlists.map((summary) => ({ kind: 'playlist' as const, summary })),
        ].sort((first, second) => second.summary.updated_at.localeCompare(first.summary.updated_at))
        setIndex(entries)
        if (initialPlaylistId !== null) {
          open('playlist', initialPlaylistId)
        } else if (entries.length > 0) {
          open(entries[0].kind, entries[0].summary.id)
        }
      })
      .catch((error: Error) => isCurrent && setErrorMessage(error.message))
    return () => {
      isCurrent = false
    }
  }, [open, initialPlaylistId])

  async function copy(work: () => Promise<{ name: string }>, words: string, view: View) {
    setIsBusy(true)
    setErrorMessage('')
    setMessage('')
    try {
      const copied = await work()
      setMessage(`Copied into ${words} as “${copied.name}”.`)
      setMessageView(view)
    } catch (error) {
      setErrorMessage((error as Error).message)
    } finally {
      setIsBusy(false)
    }
  }

  async function copyPlaylistLink(playlist: PublicPlaylist) {
    const address = sharedPlaylistAddress(playlist.id)
    setErrorMessage('')
    setMessageView(null)
    try {
      await navigator.clipboard.writeText(address)
      setMessage(`Copied the link to “${playlist.name}”: ${address}`)
    } catch {
      setMessage(`The link to “${playlist.name}” is ${address}`)
    }
  }

  const list = chosen?.kind === 'list' ? chosen.list : null
  const playlist = chosen?.kind === 'playlist' ? chosen.playlist : null
  const words = filter.trim().toLowerCase().split(/\s+/).filter(Boolean)
  const shownEntries = (list?.items ?? []).filter((entry) =>
    words.every((word) => `${entry.title} ${entry.source} ${entry.text}`.toLowerCase().includes(word)),
  )

  return (
    <div className="my-lists-page">
      <h1>Public lists</h1>
      <p>Lists of verses, readings, songs and more, and playlists, that members chose to share with everyone.</p>
      {errorMessage && (
        <p className="error" role="alert">
          {errorMessage}
        </p>
      )}
      {message && (
        <p role="status" className="list-save-message">
          {message}{' '}
          {messageView && (
            <button type="button" className="link-button" onClick={() => onNavigate(messageView)}>
              {messageView === 'music' ? 'Open Christian media' : 'Open My lists'}
            </button>
          )}
        </p>
      )}
      {index === null && !errorMessage && <p>Loading…</p>}
      {index !== null && index.length === 0 && <p>No lists or playlists have been shared yet.</p>}
      {index !== null && index.length > 0 && (
        <ul className="my-lists-index" aria-label="Shared lists and playlists">
          {index.map((entry) => {
            const isChosen =
              (entry.kind === 'list' && list?.id === entry.summary.id) || (entry.kind === 'playlist' && playlist?.id === entry.summary.id)
            return (
              <li key={`${entry.kind}-${entry.summary.id}`}>
                <button
                  type="button"
                  className={isChosen ? 'secondary-button is-chosen' : 'secondary-button'}
                  aria-current={isChosen ? 'true' : undefined}
                  onClick={() => open(entry.kind, entry.summary.id)}
                >
                  {entry.kind === 'list'
                    ? `${entry.summary.name} (${entry.summary.count}) · ${entry.summary.owner}`
                    : `Playlist: ${entry.summary.name} (${entry.summary.song_ids.length}) · ${entry.summary.owner}`}
                </button>
              </li>
            )
          })}
        </ul>
      )}
      {list && (
        <section aria-labelledby="public-list-heading">
          <h2 id="public-list-heading">{list.name}</h2>
          <p className="public-list-owner">Shared by {list.owner}</p>
          {user && (
            <div className="my-list-actions">
              <button
                type="button"
                className="secondary-button"
                disabled={isBusy || list.items.length === 0}
                onClick={() => copy(() => copyPublicList(list.id), 'My lists', 'lists')}
              >
                Copy to My lists
              </button>
            </div>
          )}
          {list.items.length > 5 && (
            <label className="my-list-filter">
              Find in this list <input type="search" value={filter} onChange={(event) => setFilter(event.target.value)} />
            </label>
          )}
          <p>
            {words.length > 0
              ? `${shownEntries.length} of ${list.items.length} ${list.items.length === 1 ? 'entry' : 'entries'}`
              : `${list.items.length} ${list.items.length === 1 ? 'entry' : 'entries'}`}
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
      {playlist && (
        <section aria-labelledby="public-playlist-heading">
          <h2 id="public-playlist-heading">Playlist: {playlist.name}</h2>
          <p className="public-list-owner">Shared by {playlist.owner}</p>
          <div className="my-list-actions">
            <button
              type="button"
              className="primary-button"
              disabled={playlist.songs.length === 0}
              onClick={() => onPlayPlaylist(playlist.name, playlist.songs.map((song) => song.id))}
            >
              Play
            </button>
            {user && (
              <button
                type="button"
                className="secondary-button"
                disabled={isBusy || playlist.songs.length === 0}
                onClick={() => copy(() => copyPublicPlaylist(playlist.id), 'your playlists', 'music')}
              >
                Copy to my playlists
              </button>
            )}
            <button type="button" className="secondary-button" onClick={() => copyPlaylistLink(playlist)}>
              Copy link
            </button>
          </div>
          <p>
            {playlist.songs.length} {playlist.songs.length === 1 ? 'song' : 'songs'}
          </p>
          {playlist.songs.length === 0 ? (
            <p>This playlist has no songs on the site now.</p>
          ) : (
            <ol className="public-playlist-songs">
              {playlist.songs.map((song) => (
                <li key={song.id}>
                  <button
                    type="button"
                    className="link-button"
                    title="Open this song on the music page"
                    onClick={() => onOpenEntry({ kind: 'music', target: { song: song.id }, title: song.title } as SavedListEntry)}
                  >
                    {song.title}
                  </button>
                  {song.author && <span className="book-result-source"> · {song.author}</span>}
                </li>
              ))}
            </ol>
          )}
        </section>
      )}
    </div>
  )
}

export default PublicListsPage
