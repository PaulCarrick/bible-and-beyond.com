import { useEffect, useRef, useState } from 'react'
import { searchInternetArchive } from './api'
import type { ArchiveItem, ArchiveKind, ArchiveResponse } from './api'
import { renderExcerpt } from './highlight'

interface ArchiveResultsProps {
  query: string
  kind: ArchiveKind
  // A new number for each search, so the same words searched again start over at page 1.
  searchId: number
}

const perPage = 10

// The links of an item, by how it can be read. A lending book is borrowed on archive.org by the visitor, an hour at a
// time, signed in with their own free Archive account; this site never borrows or copies anything.
function itemLink(item: ArchiveItem, kind: ArchiveKind) {
  if (item.access === 'borrow') {
    return 'Borrow for an hour on archive.org'
  }
  if (item.access === 'print_disabled') {
    return 'Open on archive.org (for readers with print disabilities)'
  }
  return kind === 'audio' ? 'Listen on archive.org' : 'Read on archive.org'
}

// The results of a search of the Internet Archive, shown in place of a search page's own results when "Search the
// Internet Archive" is chosen in its Match list.
function ArchiveResults({ query, kind, searchId }: ArchiveResultsProps) {
  const [page, setPage] = useState(1)
  const [shownSearch, setShownSearch] = useState(searchId)
  // The last answer and the last failure, each with the search and page it was for, so "searching" is simply
  // that neither is for the page wanted now.
  const [answer, setAnswer] = useState<{ key: string; response: ArchiveResponse } | null>(null)
  const [failure, setFailure] = useState<{ key: string; message: string } | null>(null)
  const listReference = useRef<HTMLDivElement>(null)

  // A new search starts at page 1 (set while rendering, so the old page is never asked for the new words).
  if (shownSearch !== searchId) {
    setShownSearch(searchId)
    setPage(1)
  }
  const key = `${shownSearch}:${page}`

  useEffect(() => {
    const request = new AbortController()
    searchInternetArchive({ query, kind, page, perPage }, request.signal)
      .then((found) => setAnswer({ key, response: found }))
      .catch((error) => {
        if (!request.signal.aborted) {
          setFailure({ key, message: error instanceof Error ? error.message : 'The Internet Archive could not be searched.' })
        }
      })
    return () => request.abort()
  }, [query, kind, page, key])

  const response = answer?.response ?? null
  const errorMessage = failure?.key === key ? failure.message : ''
  const isSearching = answer?.key !== key && errorMessage === ''

  function goTo(newPage: number) {
    setPage(newPage)
    listReference.current?.scrollIntoView({ block: 'nearest' })
  }

  const hasLending = response?.results.some((item) => item.access === 'borrow') ?? false

  return (
    <div className="archive-results" ref={listReference}>
      {errorMessage && <p className="error">{errorMessage}</p>}
      {isSearching && !response && <p>Searching the Internet Archive…</p>}
      {response && (
        <>
          <p className="book-search-count">
            {response.total === 0
              ? 'Nothing was found in the Internet Archive.'
              : `${response.total.toLocaleString()} ${kind === 'audio' ? 'recordings' : 'books and documents'} found in the Internet Archive`}
          </p>
          {hasLending && (
            <p className="option-note">
              Books marked <em>Borrow for an hour</em> are still under copyright. The Internet Archive lends them free,
              an hour at a time: sign in on archive.org with a free Archive account (set one up there once) and press
              Borrow. If someone else has it, the Archive offers a waiting list.
            </p>
          )}
          <ul className={`result-list book-results${isSearching ? ' is-loading' : ''}`}>
            {response.results.map((item, index) => (
              <li key={`${item.identifier}-${index}`} className="result book-result">
                <div className="book-result-place">
                  <strong>{item.title}</strong>
                  {item.creator ? ` · ${item.creator}` : ''}
                  {item.year ? ` · ${item.year}` : ''}
                </div>
                {item.snippets.map((text, number) => (
                  <p key={number} className="book-result-text">
                    {renderExcerpt(text)}
                  </p>
                ))}
                <a
                  className={item.access === 'borrow' ? 'archive-link is-borrow' : 'archive-link'}
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {itemLink(item, kind)}
                  <span className="visually-hidden"> (opens in a new tab)</span>
                </a>
              </li>
            ))}
          </ul>
          {response.last_page > 1 && (
            <nav className="pagination" aria-label="Internet Archive result pages">
              <button type="button" disabled={response.page <= 1 || isSearching} onClick={() => goTo(response.page - 1)}>
                Previous
              </button>
              <span>
                Page {response.page} of {response.last_page.toLocaleString()}
              </span>
              <button
                type="button"
                disabled={response.page >= response.last_page || isSearching}
                onClick={() => goTo(response.page + 1)}
              >
                Next
              </button>
            </nav>
          )}
          <p className="option-note">
            Results from the{' '}
            <a href="https://archive.org" target="_blank" rel="noopener noreferrer">
              Internet Archive
            </a>
            . Each opens on archive.org in a new tab.
          </p>
        </>
      )}
    </div>
  )
}

export default ArchiveResults
