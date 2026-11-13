import { useContext, useEffect, useId, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { AccountContext } from './AccountContext'
import ArchiveResults from './ArchiveResults'
import { fetchPlaylists, searchMusic } from './api'
import type { MusicSearchResponse, Playlist } from './api'
import { renderExcerpt } from './highlight'
import PlaylistSaveBox from './PlaylistSaveBox'

interface MusicSearchPageProps {
  isHidden: boolean
  // Show a song on the music page.
  onOpen: (songId: string) => void
}

type MatchMode = 'all' | 'any' | 'phrase' | 'ai' | 'archive'

interface Search {
  query: string
  matchMode: MatchMode
  page: number
  perPage: number
}

const perPage = 25

// Search the titles, authors and words of the Christian music: words in any form, all of them, any of them or
// an exact phrase. Each result has the words found in bold and a link to the song. The page stays mounted, so
// the search and its results are kept while another page is open.
//
// A logged-in visitor also gets a checkbox at the right of each result, as on the music page, and the box that
// saves the ticked songs as a playlist (PlaylistSaveBox). The ticks stay through other pages of results and
// other searches, and a new playlist plays the songs in the order they were ticked.
function MusicSearchPage({ isHidden, onOpen }: MusicSearchPageProps) {
  const queryId = useId()
  const [query, setQuery] = useState('')
  const [matchMode, setMatchMode] = useState<MatchMode>('all')
  const [response, setResponse] = useState<MusicSearchResponse | null>(null)
  // The search shown, so the pages apply to it and not to what is being typed.
  const [shown, setShown] = useState<Search | null>(null)
  const [isSearching, setIsSearching] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const controller = useRef<AbortController | null>(null)
  const { user } = useContext(AccountContext)
  // "Use AI" is only for a logged-in account an administrator allowed (the server checks too).
  const canUseAi = user?.open_ai_queries === true
  const effectiveMatchMode = matchMode === 'ai' && !canUseAi ? 'all' : matchMode
  // The Internet Archive search shown (ArchiveResults does the searching), with a new number for each search.
  const [archiveSearch, setArchiveSearch] = useState<{ query: string; id: number } | null>(null)
  // Songs ticked for a playlist, in the order they were ticked, and the visitor's playlists (for the save box).
  const [tickedIds, setTickedIds] = useState<string[]>([])
  const [playlists, setPlaylists] = useState<Playlist[]>([])
  const [playlistName, setPlaylistName] = useState('')
  const userId = user?.id ?? null

  // Nothing of the last visitor's stays after logging out or in as someone else.
  const [shownUserId, setShownUserId] = useState(userId)
  if (shownUserId !== userId) {
    setShownUserId(userId)
    setTickedIds([])
    setPlaylists([])
    setPlaylistName('')
  }

  // The visitor's playlists, each time the page is opened (one may have been saved on the music page).
  useEffect(() => {
    if (userId === null || isHidden) {
      return
    }
    const request = new AbortController()
    fetchPlaylists(request.signal)
      .then(setPlaylists)
      .catch(() => undefined)
    return () => request.abort()
  }, [userId, isHidden])

  function toggleTick(songId: string, isTicked: boolean) {
    setTickedIds((current) => (isTicked ? [...current.filter((id) => id !== songId), songId] : current.filter((id) => id !== songId)))
  }

  async function run(search: Search) {
    controller.current?.abort()
    const request = new AbortController()
    controller.current = request
    setIsSearching(true)
    setErrorMessage('')
    try {
      const found = await searchMusic(search, request.signal)
      if (!request.signal.aborted) {
        setResponse(found)
        setShown(search)
      }
    } catch (error) {
      if (!request.signal.aborted) {
        setErrorMessage(error instanceof Error ? error.message : 'The search could not be done.')
      }
    } finally {
      if (!request.signal.aborted) {
        setIsSearching(false)
      }
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (query.trim() === '') {
      return
    }
    if (effectiveMatchMode === 'archive') {
      controller.current?.abort()
      setResponse(null)
      setShown(null)
      setArchiveSearch((last) => ({ query: query.trim(), id: (last?.id ?? 0) + 1 }))
      return
    }
    setArchiveSearch(null)
    run({ query: query.trim(), matchMode: effectiveMatchMode, page: 1, perPage })
  }

  const pageCount = response ? Math.max(1, Math.ceil(response.total / response.per_page)) : 1

  return (
    <div className="welcome book-search" hidden={isHidden}>
      <h1>Search the media</h1>
      <p>
        Find a song by its title, its author or its words. Words are found in any form (<em>sing</em> also finds{' '}
        <em>singing</em>); put a phrase in quotation marks to keep it together.
      </p>

      <form className="book-search-form" onSubmit={handleSubmit}>
        <label htmlFor={queryId} className="visually-hidden">
          Words to search for
        </label>
        <div className="search-row">
          <input
            id={queryId}
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={effectiveMatchMode === 'ai' ? 'Example: songs about heaven' : 'Example "amazing grace" or soul'}
          />
          <button type="submit" className="primary-button" disabled={query.trim() === '' || isSearching}>
            {effectiveMatchMode === 'ai' ? 'Find songs with AI' : effectiveMatchMode === 'archive' ? 'Search the Internet Archive' : 'Search the media'}
          </button>
        </div>
        <div className="book-search-options">
          <label>
            Match{' '}
            <select value={effectiveMatchMode} onChange={(event) => setMatchMode(event.target.value as MatchMode)}>
              <option value="all">All the words</option>
              <option value="any">Any of the words</option>
              <option value="phrase">The exact phrase</option>
              {canUseAi && <option value="ai">Use AI to find related songs</option>}
              <option value="archive">Search the Internet Archive</option>
            </select>
          </label>
        </div>
        {effectiveMatchMode === 'archive' && (
          <p className="option-note">
            Searches the recordings of the Internet Archive (archive.org): hymns, sermons and music. The results open on
            archive.org; check each recording's licence there before using it elsewhere.
          </p>
        )}
        {effectiveMatchMode === 'ai' && (
          <p className="option-note">
            AI finds the songs whose words are closest in meaning to what you type, closest first. It can be wrong.
          </p>
        )}
      </form>

      {user && (
        <PlaylistSaveBox
          tickedIds={tickedIds}
          playlists={playlists}
          name={playlistName}
          onNameChange={setPlaylistName}
          onSaved={(playlist) => {
            setPlaylists((current) => [...current.filter((entry) => entry.id !== playlist.id), playlist])
            setTickedIds([])
          }}
          onClear={() => setTickedIds([])}
          afterSaving="Play it from Your playlists on the Listen to the media page."
        />
      )}
      {archiveSearch && <ArchiveResults query={archiveSearch.query} kind="audio" searchId={archiveSearch.id} />}
      <div>
        {errorMessage && <p className="error">{errorMessage}</p>}
        {isSearching && !response && <p>Searching…</p>}
        {response && (
          <>
            <p className="book-search-count">
              {response.total === 0 ? 'Nothing was found.' : `${response.total.toLocaleString()} ${response.total === 1 ? 'song' : 'songs'} found`}
            </p>
            {user && response.results.length > 0 && <p className="music-tick-heading">Tick songs for a playlist</p>}
            <ul className={`result-list book-results${isSearching ? ' is-loading' : ''}`}>
              {response.results.map((result) => (
                <li key={result.id} className={user ? 'result book-result music-search-result' : 'result book-result'}>
                  <div className="music-search-result-body">
                    <div className="book-result-place">
                      <strong>{result.title}</strong>
                      {result.author ? ` · ${result.author}` : ''}
                      {result.kind === 'video' ? ' · video' : ''}
                    </div>
                    <p className="book-result-text">{renderExcerpt(result.text)}</p>
                    <button type="button" className="link-button" onClick={() => onOpen(result.id)}>
                      Play this song
                    </button>
                  </div>
                  {user && (
                    <input
                      type="checkbox"
                      className="music-tick"
                      checked={tickedIds.includes(result.id)}
                      onChange={(event) => toggleTick(result.id, event.target.checked)}
                      aria-label={`Add ${result.title} to a playlist`}
                      title="Tick to add this song to a playlist"
                    />
                  )}
                </li>
              ))}
            </ul>
            {pageCount > 1 && shown && (
              <nav className="pagination" aria-label="Result pages">
                <button type="button" disabled={response.page <= 1 || isSearching} onClick={() => run({ ...shown, page: response.page - 1 })}>
                  Previous
                </button>
                <span>
                  Page {response.page} of {pageCount}
                </span>
                <button type="button" disabled={response.page >= pageCount || isSearching} onClick={() => run({ ...shown, page: response.page + 1 })}>
                  Next
                </button>
              </nav>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default MusicSearchPage
