import { useContext, useId, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { AccountContext } from './AccountContext'
import { searchOtherBooks } from './api'
import type { BookSearchOptions, BookSearchResponse } from './api'
import { renderExcerpt } from './highlight'
import type { DevotionalInfo } from './types'

interface BookSearchPageProps {
  books: DevotionalInfo[]
  isHidden: boolean
  // Open the books reader at a chapter.
  onOpen: (book: string, section: number, unit: number) => void
}

const perPage = 25

// Search inside the Other books: words in any form, all of them, any of them or an exact phrase, in every book
// or one. Each result is a passage with the words found in bold and a link to read its chapter. The page stays
// mounted, so the search and its results are kept while another page is open.
function BookSearchPage({ books, isHidden, onOpen }: BookSearchPageProps) {
  const queryId = useId()
  const [query, setQuery] = useState('')
  const [matchMode, setMatchMode] = useState<BookSearchOptions['matchMode']>('all')
  const [book, setBook] = useState('')
  const [sortBy, setSortBy] = useState<'' | 'order'>('')
  const [response, setResponse] = useState<BookSearchResponse | null>(null)
  // The search shown, so the pages, the book and the order apply to it and not to what is being typed.
  const [shown, setShown] = useState<BookSearchOptions | null>(null)
  const [isSearching, setIsSearching] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const controller = useRef<AbortController | null>(null)
  const resultsReference = useRef<HTMLDivElement>(null)
  const { user } = useContext(AccountContext)
  // "Use AI" is only for a logged-in account an administrator allowed (the server checks too).
  const canUseAi = user?.open_ai_queries === true
  const effectiveMatchMode = matchMode === 'ai' && !canUseAi ? 'all' : matchMode

  async function run(options: BookSearchOptions) {
    controller.current?.abort()
    const request = new AbortController()
    controller.current = request
    setIsSearching(true)
    setErrorMessage('')
    try {
      const found = await searchOtherBooks(options, request.signal)
      if (request.signal.aborted) {
        return
      }
      setResponse(found)
      setShown(options)
      resultsReference.current?.scrollIntoView({ block: 'nearest' })
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
    if (query.trim() !== '') {
      run({ query: query.trim(), matchMode: effectiveMatchMode, book, sortBy, page: 1, perPage })
    }
  }

  // The book and the order apply at once to the search shown; the match choice waits for Search.
  function chooseBook(newBook: string) {
    setBook(newBook)
    if (shown) {
      run({ ...shown, book: newBook, page: 1 })
    }
  }

  function chooseSort(newSort: '' | 'order') {
    setSortBy(newSort)
    if (shown) {
      run({ ...shown, sortBy: newSort, page: 1 })
    }
  }

  const counts = new Map(response?.book_counts.map((entry) => [entry.book, entry.count]) ?? [])
  const pageCount = response ? Math.max(1, Math.ceil(response.total / response.per_page)) : 1
  const allCount = response?.book_counts.reduce((sum, entry) => sum + entry.count, 0) ?? 0

  return (
    <div className="welcome book-search" hidden={isHidden}>
      <h1>Search the other books</h1>
      <p>
        Find words or a phrase in the other books. Words are found in any form (<em>love</em> also finds{' '}
        <em>loved</em> and <em>loving</em>); put a phrase in quotation marks to keep it together.
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
            placeholder={effectiveMatchMode === 'ai' ? 'Example: pride and humility' : 'Example "grace of God" or humility'}
          />
          <button type="submit" className="primary-button" disabled={query.trim() === '' || isSearching}>
            {effectiveMatchMode === 'ai' ? 'Find passages with AI' : 'Search the other books'}
          </button>
        </div>
        <div className="book-search-options">
          <label>
            Match{' '}
            <select value={effectiveMatchMode} onChange={(event) => setMatchMode(event.target.value as BookSearchOptions['matchMode'])}>
              <option value="all">All the words</option>
              <option value="any">Any of the words</option>
              <option value="phrase">The exact phrase</option>
              {canUseAi && <option value="ai">Use AI to find related passages</option>}
            </select>
          </label>
          <label>
            In{' '}
            <select value={book} onChange={(event) => chooseBook(event.target.value)}>
              <option value="">All books{response ? ` (${allCount})` : ''}</option>
              {books.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.name}
                  {response ? ` (${counts.get(entry.id) ?? 0})` : ''}
                </option>
              ))}
            </select>
          </label>
          <label hidden={shown?.matchMode === 'ai'}>
            Order{' '}
            <select value={sortBy} onChange={(event) => chooseSort(event.target.value as '' | 'order')}>
              <option value="">Best match first</option>
              <option value="order">In the order of the books</option>
            </select>
          </label>
        </div>
        {effectiveMatchMode === 'ai' && (
          <p className="option-note">
            AI finds the passages closest in meaning to what you type, even when they use other words. Up to 50,
            closest first. It can be wrong, so read each one in its chapter.
          </p>
        )}
      </form>

      <div ref={resultsReference}>
        {errorMessage && <p className="error">{errorMessage}</p>}
        {isSearching && !response && <p>Searching…</p>}
        {response && (
          <>
            <p className="book-search-count">
              {response.total === 0
                ? 'Nothing was found.'
                : `${response.total.toLocaleString()} ${response.total === 1 ? 'passage' : 'passages'} found`}
            </p>
            <ul className={`result-list book-results${isSearching ? ' is-loading' : ''}`}>
              {response.results.map((result) => (
                <li key={`${result.book}-${result.section}-${result.unit}-${result.text.slice(0, 20)}`} className="result book-result">
                  <div className="book-result-place">
                    <strong>{result.book_name}</strong>
                    {[result.section_title !== result.book_name ? result.section_title : '', result.unit_title, result.heading]
                      .filter((part) => part !== '')
                      .map((part) => ` · ${part}`)
                      .join('')}
                  </div>
                  <p className="book-result-text">{renderExcerpt(result.text)}</p>
                  <button type="button" className="link-button" onClick={() => onOpen(result.book, result.section, result.unit)}>
                    Read this chapter
                  </button>
                </li>
              ))}
            </ul>
            {pageCount > 1 && shown && (
              <nav className="pagination" aria-label="Result pages">
                <button type="button" disabled={response.page <= 1 || isSearching} onClick={() => run({ ...shown, page: 1 })}>
                  First
                </button>
                <button type="button" disabled={response.page <= 1 || isSearching} onClick={() => run({ ...shown, page: response.page - 1 })}>
                  Previous
                </button>
                <span>
                  Page {response.page} of {pageCount}
                </span>
                <button type="button" disabled={response.page >= pageCount || isSearching} onClick={() => run({ ...shown, page: response.page + 1 })}>
                  Next
                </button>
                <button type="button" disabled={response.page >= pageCount || isSearching} onClick={() => run({ ...shown, page: pageCount })}>
                  Last
                </button>
              </nav>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default BookSearchPage
