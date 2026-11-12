import { useContext, useId, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { AccountContext } from './AccountContext'
import ArchiveResults from './ArchiveResults'
import { searchEverything } from './api'
import type { SiteSearchGroup, SiteSearchKind, SiteSearchResult } from './api'
import { highlight, renderExcerpt } from './highlight'
import type { Destination } from './types'
import { verseButtonProps } from './verseAddress'
import type { View } from './views'

interface WelcomeSearchProps {
  isHidden: boolean
  // On its own page (Search everything in the sidebar) rather than under the welcome cards.
  isPage: boolean
  // Open a reader at a place: the Bible, the commentaries, the devotionals or the other books.
  onOpen: (destination: Destination, view: View) => void
  // Show a song on the music page.
  onOpenSong: (songId: string) => void
}

const perGroup = 5

type MatchMode = 'all' | 'any' | 'phrase' | 'ai' | 'archive'

const groupTitles: Record<SiteSearchKind, string> = {
  bible: 'The Bible',
  commentary: 'Commentaries',
  devotional: 'Devotionals',
  book: 'Other books',
  music: 'Christian music',
}

const hitWords: Record<SiteSearchKind, string> = { bible: 'verse', commentary: 'note', devotional: 'reading', book: 'passage', music: 'song' }

function countLabel(kind: SiteSearchKind, total: number) {
  return `${total.toLocaleString()} ${hitWords[kind]}${total === 1 ? '' : 's'}`
}

// The search form under the welcome cards: one search over the Bible (one Bible, so a verse is listed once), the
// commentaries, the devotionals and the other books. The hits come in groups, a few of each with "Show more",
// and each opens its reader at that place. It stays mounted, so the hits are still there after going Back.
function WelcomeSearch({ isHidden, isPage, onOpen, onOpenSong }: WelcomeSearchProps) {
  const queryId = useId()
  const [query, setQuery] = useState('')
  const [matchMode, setMatchMode] = useState<MatchMode>('all')
  const [searched, setSearched] = useState<{ query: string; matchMode: MatchMode } | null>(null)
  const [groups, setGroups] = useState<SiteSearchGroup[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [loadingMore, setLoadingMore] = useState<SiteSearchKind | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  // An AI search whose Bible verses could not be suggested (Gemini was busy); the other groups still show.
  const [bibleUnavailable, setBibleUnavailable] = useState(false)
  // A new number for each Internet Archive search (ArchiveResults does the searching).
  const [archiveSearchId, setArchiveSearchId] = useState(0)
  const controller = useRef<AbortController | null>(null)
  const { user } = useContext(AccountContext)
  // "Use AI" is only for a logged-in account an administrator allowed (the server checks too).
  const canUseAi = user?.open_ai_queries === true
  const effectiveMatchMode = matchMode === 'ai' && !canUseAi ? 'all' : matchMode

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const wanted = { query: query.trim(), matchMode: effectiveMatchMode }
    if (wanted.query === '') {
      return
    }
    controller.current?.abort()
    if (wanted.matchMode === 'archive') {
      setGroups([])
      setBibleUnavailable(false)
      setErrorMessage('')
      setIsSearching(false)
      setSearched(wanted)
      setArchiveSearchId((number) => number + 1)
      return
    }
    const request = new AbortController()
    controller.current = request
    setIsSearching(true)
    setErrorMessage('')
    try {
      const found = await searchEverything({ ...wanted, page: 1, perPage: perGroup }, request.signal)
      if (!request.signal.aborted) {
        setGroups(found.groups)
        setBibleUnavailable(found.bible_unavailable === true)
        setSearched(wanted)
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

  async function showMore(group: SiteSearchGroup) {
    if (!searched) {
      return
    }
    setLoadingMore(group.kind)
    setErrorMessage('')
    try {
      const found = await searchEverything(
        { ...searched, kind: group.kind, page: group.page + 1, perPage: perGroup },
        new AbortController().signal,
      )
      const next = found.groups[0]
      setGroups((shown) =>
        shown.map((entry) =>
          entry.kind === group.kind ? { ...entry, page: next.page, results: [...entry.results, ...next.results] } : entry,
        ),
      )
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'More could not be loaded.')
    } finally {
      setLoadingMore(null)
    }
  }

  function renderHit(group: SiteSearchGroup, result: SiteSearchResult): { place: ReactNode; text: ReactNode; link: ReactNode } {
    if (result.kind === 'bible') {
      const verse = { translation: result.translation, book: result.book_number, chapter: result.chapter, verse: result.verse }
      return {
        place: <strong>{result.reference}</strong>,
        text: highlight(result.text, group.terms ?? [], true),
        link: (
          <button
            type="button"
            className="link-button"
            {...verseButtonProps(verse, () => onOpen({ id: Date.now(), kind: 'bible', ...verse }, 'read'))}
          >
            Read in the Bible
          </button>
        ),
      }
    }
    if (result.kind === 'commentary') {
      return {
        place: (
          <>
            <strong>{result.commentary_name}</strong> on {result.reference}
          </>
        ),
        text: renderExcerpt(result.text),
        link: (
          <button
            type="button"
            className="link-button"
            onClick={() =>
              onOpen(
                { id: Date.now(), kind: 'commentary', commentary: result.commentary_id, book: result.book_number, chapter: result.chapter, verse: result.verse },
                'browse',
              )
            }
          >
            Read the note
          </button>
        ),
      }
    }
    if (result.kind === 'music') {
      return {
        place: (
          <>
            <strong>{result.title}</strong>
            {result.author ? ` · ${result.author}` : ''}
          </>
        ),
        text: renderExcerpt(result.text),
        link: (
          <button type="button" className="link-button" onClick={() => onOpenSong(result.id)}>
            Play this song
          </button>
        ),
      }
    }
    const parts = [result.section_title !== result.book_name ? result.section_title : '', result.unit_title, result.heading].filter(
      (part) => part !== '',
    )
    return {
      place: (
        <>
          <strong>{result.book_name}</strong>
          {parts.map((part) => ` · ${part}`).join('')}
        </>
      ),
      text: renderExcerpt(result.text),
      link: (
        <button
          type="button"
          className="link-button"
          onClick={() =>
            onOpen(
              { id: Date.now(), kind: 'devotional', devotional: result.book, section: result.section, unit: result.unit },
              group.kind === 'book' ? 'books' : 'devotionals',
            )
          }
        >
          {group.kind === 'book' ? 'Read this chapter' : 'Read this reading'}
        </button>
      ),
    }
  }

  return (
    <section
      className={`welcome welcome-search${isPage ? ' is-page' : ''}`}
      hidden={isHidden}
      aria-labelledby={`${queryId}-heading`}
    >
      {isPage ? <h1 id={`${queryId}-heading`}>Search everything</h1> : <h2 id={`${queryId}-heading`}>Search everything</h2>}
      <p>Search the Bible, the commentaries, the devotionals, the other books and the Christian music at once.</p>
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
            placeholder={effectiveMatchMode === 'ai' ? 'Example: the beatitudes' : 'Example "born again" or forgiveness'}
          />
          <button type="submit" className="primary-button" disabled={query.trim() === '' || isSearching}>
            {effectiveMatchMode === 'ai' ? 'Search with AI' : effectiveMatchMode === 'archive' ? 'Search the Internet Archive' : 'Search'}
          </button>
        </div>
        <div className="book-search-options">
          <label>
            Match{' '}
            <select value={effectiveMatchMode} onChange={(event) => setMatchMode(event.target.value as MatchMode)}>
              <option value="all">All the words</option>
              <option value="any">Any of the words</option>
              <option value="phrase">The exact phrase</option>
              {canUseAi && <option value="ai">Use AI to find related passages</option>}
              <option value="archive">Search the Internet Archive</option>
            </select>
          </label>
        </div>
        {effectiveMatchMode === 'archive' && (
          <p className="option-note">
            Searches inside the books and documents of the Internet Archive (archive.org), including its lending library
            of books still under copyright, which anyone can borrow free for an hour with an Archive account. The
            results open on archive.org.
          </p>
        )}
        {effectiveMatchMode === 'ai' && (
          <p className="option-note">
            AI finds what is closest in meaning to what you type, even in other words: an AI (Google&rsquo;s Gemini)
            suggests the Bible verses, and the commentaries, devotionals, other books and songs are those nearest in
            meaning, closest first. It can be wrong, so read each one in its place.
          </p>
        )}
      </form>

      {errorMessage && <p className="error">{errorMessage}</p>}
      {isSearching && <p>Searching…</p>}
      {bibleUnavailable && !isSearching && (
        <p className="option-note">
          The AI could not suggest Bible verses just now (it was too busy); try the search again in a minute for them.
        </p>
      )}
      {searched?.matchMode === 'archive' && <ArchiveResults query={searched.query} kind="texts" searchId={archiveSearchId} />}
      {searched && searched.matchMode !== 'archive' && !isSearching && groups.length === 0 && !errorMessage && <p>Nothing was found.</p>}
      {groups.map((group) => (
        <div key={group.kind} className={`welcome-search-group${isSearching ? ' is-loading' : ''}`}>
          <h3>
            {groupTitles[group.kind]}
            {group.kind === 'bible' && group.translation ? ` (${group.translation})` : ''}
            <span className="welcome-search-count"> · {countLabel(group.kind, group.total)}</span>
          </h3>
          <ul className="result-list book-results">
            {group.results.map((result, index) => {
              const hit = renderHit(group, result)
              return (
                <li key={index} className="result book-result">
                  <div className="book-result-place">{hit.place}</div>
                  <p className="book-result-text">{hit.text}</p>
                  {hit.link}
                </li>
              )
            })}
          </ul>
          {group.results.length < group.total && (
            <button type="button" className="welcome-search-more" disabled={loadingMore !== null} onClick={() => showMore(group)}>
              {loadingMore === group.kind ? 'Loading…' : `Show more ${hitWords[group.kind]}s`}
            </button>
          )}
        </div>
      ))}
    </section>
  )
}

export default WelcomeSearch
