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

// Public lists (under Members; the owner's request, 2026-11-19): the lists members shared from My lists (accounts an
// administrator allowed to share), for everyone who can use the site. Each shows who shared it and its entries,
// which open where they came from; a logged-in member can copy one into their own lists. Shared playlists (2026-11-21,
// the owner's request) are listed after the lists: Play plays one on the music page, and a logged-in visitor can copy
// one into their own playlists. A link to one (/public-lists?playlist=12) opens it here.
function PublicListsPage({ onOpenEntry, onNavigate, onPlayPlaylist, initialPlaylistId }: PublicListsPageProps) {
  const { user } = useContext(AccountContext)
  const [lists, setLists] = useState<SavedListSummary[] | null>(null)
  const [chosen, setChosen] = useState<SavedList | null>(null)
  const [filter, setFilter] = useState('')
  const [message, setMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [isBusy, setIsBusy] = useState(false)
  const [playlists, setPlaylists] = useState<Playlist[] | null>(null)
  const [chosenPlaylist, setChosenPlaylist] = useState<PublicPlaylist | null>(null)
  const [playlistMessage, setPlaylistMessage] = useState('')
  const [playlistError, setPlaylistError] = useState('')

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

  const openPlaylist = useCallback(async (id: number, scroll = false) => {
    setPlaylistError('')
    setPlaylistMessage('')
    try {
      setChosenPlaylist(await fetchPublicPlaylist(id))
      if (scroll) {
        requestAnimationFrame(() => document.getElementById('public-playlists-heading')?.scrollIntoView({ block: 'start' }))
      }
    } catch (error) {
      setPlaylistError((error as Error).message)
    }
  }, [])

  useEffect(() => {
    let isCurrent = true
    fetchPublicPlaylists()
      .then((found) => {
        if (!isCurrent) {
          return
        }
        setPlaylists(found)
        if (initialPlaylistId !== null) {
          openPlaylist(initialPlaylistId, true)
        } else if (found.length > 0) {
          openPlaylist(found[0].id)
        }
      })
      .catch((error: Error) => isCurrent && setPlaylistError(error.message))
    return () => {
      isCurrent = false
    }
  }, [openPlaylist, initialPlaylistId])

  async function copyPlaylist(playlist: PublicPlaylist) {
    setIsBusy(true)
    setPlaylistError('')
    setPlaylistMessage('')
    try {
      const copied = await copyPublicPlaylist(playlist.id)
      setPlaylistMessage(`Copied into your playlists as “${copied.name}”.`)
    } catch (error) {
      setPlaylistError((error as Error).message)
    } finally {
      setIsBusy(false)
    }
  }

  async function copyPlaylistLink(playlist: PublicPlaylist) {
    const address = sharedPlaylistAddress(playlist.id)
    try {
      await navigator.clipboard.writeText(address)
      setPlaylistMessage(`Copied the link to “${playlist.name}”: ${address}`)
    } catch {
      setPlaylistMessage(`The link to “${playlist.name}” is ${address}`)
    }
  }

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
      <p>Lists of verses, readings, songs and more, and playlists, that members chose to share with everyone.</p>
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

      <h2 id="public-playlists-heading">Shared playlists</h2>
      {playlistError && (
        <p className="error" role="alert">
          {playlistError}
        </p>
      )}
      {playlistMessage && (
        <p role="status" className="list-save-message">
          {playlistMessage}{' '}
          {playlistMessage.startsWith('Copied into') && (
            <button type="button" className="link-button" onClick={() => onNavigate('music')}>
              Open Christian media
            </button>
          )}
        </p>
      )}
      {playlists === null && !playlistError && <p>Loading…</p>}
      {playlists !== null && playlists.length === 0 && <p>No playlists have been shared yet.</p>}
      {playlists !== null && playlists.length > 0 && (
        <ul className="my-lists-index" aria-label="Shared playlists">
          {playlists.map((playlist) => (
            <li key={playlist.id}>
              <button
                type="button"
                className={chosenPlaylist?.id === playlist.id ? 'secondary-button is-chosen' : 'secondary-button'}
                aria-current={chosenPlaylist?.id === playlist.id ? 'true' : undefined}
                onClick={() => openPlaylist(playlist.id)}
              >
                {playlist.name} ({playlist.song_ids.length}) · {playlist.owner}
              </button>
            </li>
          ))}
        </ul>
      )}
      {chosenPlaylist && (
        <section aria-labelledby="public-playlist-heading">
          <h3 id="public-playlist-heading">{chosenPlaylist.name}</h3>
          <p className="public-list-owner">Shared by {chosenPlaylist.owner}</p>
          <div className="my-list-actions">
            <button
              type="button"
              className="primary-button"
              disabled={chosenPlaylist.songs.length === 0}
              onClick={() => onPlayPlaylist(chosenPlaylist.name, chosenPlaylist.songs.map((song) => song.id))}
            >
              Play
            </button>
            {user && (
              <button type="button" className="secondary-button" disabled={isBusy || chosenPlaylist.songs.length === 0} onClick={() => copyPlaylist(chosenPlaylist)}>
                Copy to my playlists
              </button>
            )}
            <button type="button" className="secondary-button" onClick={() => copyPlaylistLink(chosenPlaylist)}>
              Copy link
            </button>
          </div>
          {chosenPlaylist.songs.length === 0 ? (
            <p>This playlist has no songs on the site now.</p>
          ) : (
            <ol className="public-playlist-songs">
              {chosenPlaylist.songs.map((song) => (
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
