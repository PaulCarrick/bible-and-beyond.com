import { useEffect, useRef } from 'react'
import ContextWindow from './ContextWindow'
import { reportView } from './fums'
import { highlight, renderExcerpt } from './highlight'
import { parsePerPage, perPageOptions } from './perPage'
import { useVerseWindows } from './useVerseWindows'
import type {
  Book,
  PerPage,
  SearchParameters,
  SearchResponse,
  ContextKind,
  SearchResult,
  SortField,
} from './types'

// Space needed below the list for the page buttons, the collapsed options bar, and padding.
const heightBelowList = 140
// Each batch of results gives a better average row height, so measure a few times per search.
const maximumMeasurements = 3
const resizeDelayMilliseconds = 250
const maximumPerPage = 100

function calculateFitCount(
  list: HTMLOListElement | null,
  rowHeight: number,
  extraHeightBelowList: number,
) {
  // A hidden list (for example while the copyright page is open) has no size to measure.
  if (list === null || list.offsetParent === null || rowHeight === 0) {
    return null
  }
  const listTop = list.getBoundingClientRect().top + window.scrollY
  // The footer is below the results and the reader scrolls to it, so it takes no room from the rows.
  const availableHeight = window.innerHeight - listTop - heightBelowList - extraHeightBelowList
  return Math.min(maximumPerPage, Math.max(1, Math.floor(availableHeight / rowHeight)))
}

const sortColumns: { field: SortField; label: string; className: string }[] = [
  { field: 'verse', label: 'Verse', className: 'reference' },
  { field: 'text', label: 'Contents', className: 'verse-text' },
]

interface SearchResultsProps {
  // Whether the results are verses of Bibles or notes of commentaries.
  mode: 'bible' | 'commentary'
  // The Bible that "Show in Context" uses for a commentary result.
  contextTranslation: string
  // What a commentary search looked through ("all commentaries" or one name), for the heading.
  sourceLabel: string
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
  onShowCopyrights: () => void
}

function SearchResults({
  mode,
  contextTranslation,
  sourceLabel,
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
  onShowCopyrights,
}: SearchResultsProps) {
  const listReference = useRef<HTMLOListElement>(null)
  // The copyright line under licensed results takes room that the rows cannot use.
  const citationHeight = () =>
    citationReference.current ? citationReference.current.offsetHeight + 16 : 0
  const averageRowHeight = useRef(0)
  const citationReference = useRef<HTMLParagraphElement>(null)
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
    // Licensed Bibles cost a request per page, so they get a single correction.
    const measurementLimit = response.source === 'api_bible' ? 1 : maximumMeasurements
    if (measurementCount.current >= measurementLimit || list === null || list.children.length === 0) {
      return
    }
    measurementCount.current += 1
    averageRowHeight.current = list.getBoundingClientRect().height / list.children.length
    const fitCount = calculateFitCount(list, averageRowHeight.current, citationHeight())
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
        const fitCount = calculateFitCount(
          listReference.current,
          averageRowHeight.current,
          citationHeight(),
        )
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

  // API.Bible asks every site to report each time its licensed text is shown.
  useEffect(() => {
    if (response?.fums_token) {
      reportView(response.fums_token)
    }
  }, [response])

  const isLicensed = response?.source === 'api_bible'
  const windows = useVerseWindows(response, !isLoading)
  const showContext = windows.isShowing
  const currentView = windows.currentView

  // A link under a result: open a window for that verse, in place of the list.
  function openContext(kind: ContextKind, result: SearchResult, trigger: HTMLElement) {
    if (response === null) {
      return
    }
    // A commentary result is not tied to a Bible, so the verse is shown in the one chosen for that.
    windows.open(
      response,
      kind,
      {
        translation: response.source === 'commentary' ? contextTranslation : result.translation,
        book_number: result.book_number,
        chapter: result.chapter,
        verse: result.verse,
        reference: result.reference,
        // A note on a commentary result belongs to that commentary's note, not to the verse.
        ...(kind === 'note' && response.source === 'commentary'
          ? {
              reference: `${result.reference} (${result.commentary_name})`,
              subject: {
                item_type: 'commentary' as const,
                source_code: result.commentary_id ?? '',
                book_number: result.book_number,
                chapter: result.chapter,
                verse: result.verse,
              },
            }
          : {}),
      },
      trigger,
      { commentaryId: kind === 'commentary' ? (result.commentary_id ?? null) : null },
    )
  }

  // The link in the note above a Strong's number search: open that word's lexicon entry.
  function openLexicon(strongCode: string, trigger: HTMLElement) {
    if (response === null) {
      return
    }
    windows.open(
      response,
      'lexicon',
      {
        translation: response.results[0]?.translation ?? searchParameters.translations[0],
        book_number: 0,
        chapter: 0,
        verse: 0,
        reference: strongCode,
        strong_code: strongCode,
      },
      trigger,
    )
  }

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
              {response ? response.total.toLocaleString() : '…'}{' '}
              {mode === 'commentary' ? 'commentary results' : 'Bible results'} for “
              {searchParameters.query}”
            </strong>{' '}
            {mode === 'commentary' ? `in ${sourceLabel}` : `from ${searchParameters.translations.join(', ')}`}
          </p>
          {response?.strong && (
            <p className="strong-note">
              Verses with the {response.strong.language === 'hebrew' ? 'Hebrew' : 'Greek'} word{' '}
              <span
                lang={response.strong.language === 'hebrew' ? 'he' : 'el'}
                dir={response.strong.language === 'hebrew' ? 'rtl' : 'ltr'}
              >
                {response.strong.original}
              </span>{' '}
              ({response.strong.transliteration}), {response.strong.code}: {response.strong.gloss}.{' '}
              <button
                type="button"
                className="link-button"
                onClick={(event) => openLexicon(response.strong?.code ?? '', event.currentTarget)}
              >
                Open the lexicon entry
                <span className="visually-hidden"> for {response.strong.code}</span>
              </button>
            </p>
          )}
        </div>

        {errorMessage && <p className="error">{errorMessage}</p>}
        {isLoading && !response && <p>Searching…</p>}
        {response && response.total === 0 && (
          <p>{mode === 'commentary' ? 'No commentary notes matched your search.' : 'No verses matched your search.'}</p>
        )}

        <div hidden={showContext}>
          {response && response.total > 0 && (
            <div className="result-header">
              {sortColumns.map((column) => {
                if ((isLicensed || mode === 'commentary') && column.field === 'text') {
                  return (
                    <span key={column.field} className={column.className}>
                      {column.label}
                    </span>
                  )
                }
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
              {mode === 'commentary' && searchParameters.sortBy === null && (
                <span className="sort-note">Best matches first</span>
              )}
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
                  {result.reference}
                  {mode === 'commentary' ? (
                    <span className="translation-code"> {result.commentary_name}</span>
                  ) : (
                    showTranslationCode && <span className="translation-code"> {result.translation}</span>
                  )}
                </span>
                <div className="verse-column">
                  <span className="verse-text">
                    {mode === 'commentary'
                      ? renderExcerpt(result.text)
                      : highlight(result.text, response.terms, searchParameters.wholeWords)}
                  </span>
                  {response.source === 'commentary' && (
                    <div className="verse-links">
                      <button
                        type="button"
                        className="link-button context-link"
                        onClick={(event) => openContext('commentary', result, event.currentTarget)}
                      >
                        Read the note
                        <span className="visually-hidden">
                          {' '}
                          by {result.commentary_name} on {result.reference}
                        </span>
                      </button>
                      <button
                        type="button"
                        className="link-button context-link"
                        onClick={(event) => openContext('context', result, event.currentTarget)}
                      >
                        Show in Context
                        <span className="visually-hidden"> for {result.reference}</span>
                      </button>
                      <button
                        type="button"
                        className="link-button context-link"
                        onClick={(event) => openContext('note', result, event.currentTarget)}
                      >
                        Notes
                        <span className="visually-hidden"> on this note by {result.commentary_name}</span>
                      </button>
                    </div>
                  )}
                  {response.source === 'local' && (
                    <div className="verse-links">
                      <button
                        type="button"
                        className="link-button context-link"
                        onClick={(event) => openContext('context', result, event.currentTarget)}
                      >
                        Show in Context
                        <span className="visually-hidden"> for {result.reference}</span>
                      </button>
                      <button
                        type="button"
                        className="link-button context-link"
                        onClick={(event) => openContext('chapter', result, event.currentTarget)}
                      >
                        Full Chapter
                        <span className="visually-hidden"> containing {result.reference}</span>
                      </button>
                      <button
                        type="button"
                        className="link-button context-link"
                        onClick={(event) => openContext('parallel', result, event.currentTarget)}
                      >
                        Other Translations
                        <span className="visually-hidden"> of {result.reference}</span>
                      </button>
                      <button
                        type="button"
                        className="link-button context-link"
                        onClick={(event) => openContext('related', result, event.currentTarget)}
                      >
                        Related Verses
                        <span className="visually-hidden"> for {result.reference}</span>
                      </button>
                      <button
                        type="button"
                        className="link-button context-link"
                        onClick={(event) => openContext('words', result, event.currentTarget)}
                      >
                        Original Words
                        <span className="visually-hidden"> of {result.reference}</span>
                      </button>
                      <button
                        type="button"
                        className="link-button context-link"
                        onClick={(event) => openContext('commentary', result, event.currentTarget)}
                      >
                        Commentaries
                        <span className="visually-hidden"> on {result.reference}</span>
                      </button>
                      <button
                        type="button"
                        className="link-button context-link"
                        onClick={(event) => openContext('note', result, event.currentTarget)}
                      >
                        Notes
                        <span className="visually-hidden"> on {result.reference}</span>
                      </button>
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ol>

          {isLicensed && response?.copyright && (
            <p className="citation" ref={citationReference}>
              {response.copyright} Scripture text provided through{' '}
              <a href="https://api.bible" target="_blank" rel="noreferrer">
                API.Bible
              </a>
              .{' '}
              <button type="button" className="link-button" onClick={onShowCopyrights}>
                Bible copyright notices
              </button>
            </p>
          )}

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

        {showContext && currentView && (
          <ContextWindow
            key={currentView.id}
            view={currentView}
            canGoBack={windows.views.length > 1}
            terms={
              // Search words are bolded only where they were searched for: in a note after a commentary
              // search, in Bible text after a Bible search.
              windows.views.length === 1 && (response?.source === 'commentary') === (currentView.kind === 'commentary')
                ? (response?.terms ?? [])
                : []
            }
            wholeWords={searchParameters.wholeWords}
            onBack={windows.goBack}
            onClose={windows.close}
            onOpenVerse={windows.openVerse}
            onChangeDirection={windows.changeDirection}
            onChangeCommentary={windows.changeCommentary}
          />
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

        {!isLicensed && (
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
        )}
      </aside>
    </div>
  )
}

export default SearchResults
