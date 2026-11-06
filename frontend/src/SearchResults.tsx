import { useEffect, useRef } from 'react'
import { parsePerPage, perPageOptions } from './perPage'
import type { Book, PerPage, SearchParameters, SearchResponse, SortField } from './types'

// Space needed below the list for the page buttons, the collapsed options bar, and padding.
const heightBelowList = 140
// Each batch of results gives a better average row height, so measure a few times per search.
const maximumMeasurements = 3
const resizeDelayMilliseconds = 250
const maximumPerPage = 100

function calculateFitCount(list: HTMLOListElement | null, rowHeight: number) {
  if (list === null || rowHeight === 0) {
    return null
  }
  const listTop = list.getBoundingClientRect().top + window.scrollY
  const availableHeight = window.innerHeight - listTop - heightBelowList
  return Math.min(maximumPerPage, Math.max(1, Math.floor(availableHeight / rowHeight)))
}

const sortColumns: { field: SortField; label: string; className: string }[] = [
  { field: 'verse', label: 'Verse', className: 'reference' },
  { field: 'text', label: 'Contents', className: 'verse-text' },
]

interface SearchResultsProps {
  searchParameters: SearchParameters
  response: SearchResponse | null
  books: Book[]
  selectedBook: number | null
  isLoading: boolean
  errorMessage: string
  onSelectBook: (book: number | null) => void
  onChangePage: (page: number) => void
  onChangePerPage: (perPage: PerPage) => void
  onFit: (fitCount: number) => void
  onSort: (sortBy: SortField) => void
  onClearSort: () => void
}

function escapeRegularExpression(text: string) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function highlight(text: string, terms: string[], wholeWords: boolean) {
  const alternatives = terms
    .map((term) => escapeRegularExpression(term))
    .map((term) => (wholeWords ? `\\b${term}\\b` : term))
  if (alternatives.length === 0) {
    return text
  }
  const pieces = text.split(new RegExp(`(${alternatives.join('|')})`, 'i'))
  // With one capture group, split puts every match at an odd index.
  return pieces.map((piece, index) =>
    index % 2 === 1 ? <strong key={index}>{piece}</strong> : piece,
  )
}

function SearchResults({
  searchParameters,
  response,
  books,
  selectedBook,
  isLoading,
  errorMessage,
  onSelectBook,
  onChangePage,
  onChangePerPage,
  onFit,
  onSort,
  onClearSort,
}: SearchResultsProps) {
  const listReference = useRef<HTMLOListElement>(null)
  const averageRowHeight = useRef(0)
  const measurementCount = useRef(0)
  const currentPerPage = useRef(0)
  const isAutomatic = searchParameters.perPage === 'automatic'

  // As results of a search arrive, measure the real rows and ask for the page size that
  // fills the window.
  useEffect(() => {
    if (!isAutomatic || response === null) {
      measurementCount.current = 0
      return
    }
    currentPerPage.current = response.per_page
    const list = listReference.current
    if (measurementCount.current >= maximumMeasurements || list === null || list.children.length === 0) {
      return
    }
    measurementCount.current += 1
    averageRowHeight.current = list.getBoundingClientRect().height / list.children.length
    const fitCount = calculateFitCount(list, averageRowHeight.current)
    const everythingAlreadyShown = fitCount !== null && response.total <= Math.min(fitCount, response.per_page)
    if (fitCount !== null && fitCount !== response.per_page && !everythingAlreadyShown) {
      onFit(fitCount)
    }
  }, [isAutomatic, response, onFit])

  // Resizing the window changes how many rows fit.
  useEffect(() => {
    if (!isAutomatic) {
      return
    }
    let timer: number | undefined
    function handleResize() {
      window.clearTimeout(timer)
      timer = window.setTimeout(() => {
        const fitCount = calculateFitCount(listReference.current, averageRowHeight.current)
        if (fitCount !== null && fitCount !== currentPerPage.current) {
          onFit(fitCount)
        }
      }, resizeDelayMilliseconds)
    }
    window.addEventListener('resize', handleResize)
    return () => {
      window.clearTimeout(timer)
      window.removeEventListener('resize', handleResize)
    }
  }, [isAutomatic, onFit])

  const countsByBook = new Map(
    (response?.book_counts ?? []).map((entry) => [entry.book_number, entry.count]),
  )
  const totalAcrossBooks = (response?.book_counts ?? []).reduce((sum, entry) => sum + entry.count, 0)
  const testaments = [
    { label: 'Old Testament', code: 'OT' },
    { label: 'New Testament', code: 'NT' },
  ]
  const pageCount = response ? Math.max(1, Math.ceil(response.total / response.per_page)) : 1
  const showTranslationCode = searchParameters.translations.length > 1

  return (
    <div className="results-layout">
      <div className="results-main panel">
        <div className="results-heading">
          <p>
            <strong>
              {response ? response.total.toLocaleString() : '…'} Bible results for “
              {searchParameters.query}”
            </strong>{' '}
            from {searchParameters.translations.join(', ')}
          </p>
        </div>

        {errorMessage && <p className="error">{errorMessage}</p>}
        {isLoading && !response && <p>Searching…</p>}
        {response && response.total === 0 && <p>No verses matched your search.</p>}

        {response && response.total > 0 && (
          <div className="result-header">
            {sortColumns.map((column) => {
              const isSorted = searchParameters.sortBy === column.field
              const isDescending = isSorted && searchParameters.sortDirection === 'desc'
              return (
                <button
                  type="button"
                  key={column.field}
                  className={`${column.className} sort-button${isSorted ? ' sorted' : ''}`}
                  aria-sort={isSorted ? (isDescending ? 'descending' : 'ascending') : 'none'}
                  onClick={() => onSort(column.field)}
                >
                  {column.label}
                  {isSorted && <span aria-hidden="true">{isDescending ? ' ▼' : ' ▲'}</span>}
                </button>
              )
            })}
            {searchParameters.sortBy !== null && (
              <button type="button" className="link-button clear-sort" onClick={onClearSort}>
                Clear Sort
              </button>
            )}
          </div>
        )}

        <ol ref={listReference} className={isLoading ? 'result-list is-loading' : 'result-list'}>
          {response?.results.map((result) => (
            <li
              className="result"
              key={`${result.translation}-${result.book_number}-${result.chapter}-${result.verse}`}
            >
              <span className="reference">
                {result.book_name} {result.chapter}:{result.verse}
                {showTranslationCode && <span className="translation-code"> {result.translation}</span>}
              </span>
              <span className="verse-text">
                {highlight(result.text, response.terms, searchParameters.wholeWords)}
              </span>
            </li>
          ))}
        </ol>

        {response && pageCount > 1 && (
          <nav className="pagination" aria-label="Result pages">
            <button
              type="button"
              disabled={response.page <= 1}
              onClick={() => onChangePage(1)}
            >
              First
            </button>
            <button
              type="button"
              disabled={response.page <= 1}
              onClick={() => onChangePage(response.page - 1)}
            >
              Previous
            </button>
            <span>
              Page {response.page} of {pageCount}
            </span>
            <button
              type="button"
              disabled={response.page >= pageCount}
              onClick={() => onChangePage(response.page + 1)}
            >
              Next
            </button>
            <button
              type="button"
              disabled={response.page >= pageCount}
              onClick={() => onChangePage(pageCount)}
            >
              Last
            </button>
          </nav>
        )}
      </div>

      <aside className="results-sidebar">
        <label className="inline-label">
          <select
            value={searchParameters.perPage}
            onChange={(event) => onChangePerPage(parsePerPage(event.target.value))}
          >
            {perPageOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          results per page
        </label>

        <div className="panel filters">
          <h2>Filters</h2>
          <button
            type="button"
            className={selectedBook === null ? 'filter active' : 'filter'}
            onClick={() => onSelectBook(null)}
          >
            All ({totalAcrossBooks.toLocaleString()})
          </button>
          {testaments.map((testament) => {
            const testamentBooks = books.filter(
              (book) => book.testament === testament.code && countsByBook.has(book.number),
            )
            if (testamentBooks.length === 0) {
              return null
            }
            const testamentTotal = testamentBooks.reduce(
              (sum, book) => sum + (countsByBook.get(book.number) ?? 0),
              0,
            )
            return (
              <div key={testament.code}>
                <h3>
                  {testament.label} ({testamentTotal.toLocaleString()})
                </h3>
                {testamentBooks.map((book) => (
                  <button
                    type="button"
                    key={book.number}
                    className={selectedBook === book.number ? 'filter active' : 'filter'}
                    onClick={() => onSelectBook(book.number)}
                  >
                    {book.name} ({countsByBook.get(book.number)})
                  </button>
                ))}
              </div>
            )
          })}
        </div>
      </aside>
    </div>
  )
}

export default SearchResults
