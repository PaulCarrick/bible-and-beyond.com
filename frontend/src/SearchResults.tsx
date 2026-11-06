import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchContext, fetchLexiconEntry, fetchOriginalWords, fetchParallel, fetchRelated } from './api'
import ContextWindow from './ContextWindow'
import type { WindowView } from './ContextWindow'
import { reportView } from './fums'
import { highlight } from './highlight'
import { parsePerPage, perPageOptions } from './perPage'
import type {
  Book,
  PerPage,
  SearchParameters,
  SearchResponse,
  ContextKind,
  RelatedDirection,
  SearchResult,
  SortField,
  VerseTarget,
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
  const footer = document.querySelector('.site-footer')
  const footerHeight = footer
    ? footer.getBoundingClientRect().height + parseFloat(getComputedStyle(footer).marginTop)
    : 0
  const availableHeight =
    window.innerHeight - listTop - heightBelowList - extraHeightBelowList - footerHeight
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
  onShowCopyrights: () => void
}

interface WindowState {
  // The results that were on screen when the window was opened. A new search closes the window.
  openedFor: SearchResponse
  // The windows opened one from another; the last one is showing and Back removes it.
  views: WindowView[]
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
  onShowCopyrights,
}: SearchResultsProps) {
  const [windowState, setWindowState] = useState<WindowState | null>(null)
  const contextRequest = useRef<AbortController | null>(null)
  const contextTrigger = useRef<HTMLElement | null>(null)
  const nextViewId = useRef(1)
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
    const measurementLimit = response.source === 'local' ? maximumMeasurements : 1
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
  const showContext = windowState !== null && windowState.openedFor === response && !isLoading
  const currentView = windowState ? windowState.views[windowState.views.length - 1] : null

  function updateView(id: number, changes: Partial<WindowView>) {
    setWindowState((current) =>
      current
        ? { ...current, views: current.views.map((view) => (view.id === id ? { ...view, ...changes } : view)) }
        : current,
    )
  }

  // Ask the server for what a window shows, and put the answer in that window.
  function loadView(view: WindowView) {
    contextRequest.current?.abort()
    const controller = new AbortController()
    contextRequest.current = controller

    const { translation, book_number: book, chapter, verse } = view.target
    const request =
      view.kind === 'parallel'
        ? fetchParallel(book, chapter, verse, controller.signal).then((parallel) => ({ parallel }))
        : view.kind === 'related'
          ? fetchRelated(translation, book, chapter, verse, view.direction, controller.signal).then(
              (related) => ({ related }),
            )
          : view.kind === 'words'
            ? fetchOriginalWords(book, chapter, verse, controller.signal).then((words) => ({ words }))
            : view.kind === 'lexicon'
              ? fetchLexiconEntry(translation, view.target.strong_code ?? '', controller.signal).then(
                  (lexicon) => ({ lexicon }),
                )
              : fetchContext(view.kind, translation, book, chapter, verse, controller.signal).then(
                  (context) => ({ context }),
                )
    request
      .then((answer) => updateView(view.id, { ...answer, errorMessage: '' }))
      .catch((error) => {
        if (controller.signal.aborted) {
          return
        }
        const errorMessage = error instanceof Error ? error.message : 'Could not load the verses.'
        updateView(view.id, { errorMessage })
      })
  }

  function newView(kind: ContextKind, target: VerseTarget, direction: RelatedDirection = 'from'): WindowView {
    const id = nextViewId.current
    nextViewId.current += 1
    return {
      id,
      kind,
      target,
      direction,
      context: null,
      parallel: null,
      related: null,
      words: null,
      lexicon: null,
      errorMessage: '',
    }
  }

  // A link under a result: open a window for that verse, in place of the list.
  function openContext(kind: ContextKind, result: SearchResult, trigger: HTMLElement) {
    if (response === null) {
      return
    }
    contextTrigger.current = trigger
    const view = newView(kind, {
      translation: result.translation,
      book_number: result.book_number,
      chapter: result.chapter,
      verse: result.verse,
      reference: result.reference,
    })
    setWindowState({ openedFor: response, views: [view] })
    loadView(view)
  }

  // The link in the note above a Strong's number search: open that word's lexicon entry.
  function openLexicon(strongCode: string, trigger: HTMLElement) {
    if (response === null) {
      return
    }
    contextTrigger.current = trigger
    const view = newView('lexicon', {
      translation: response.results[0]?.translation ?? searchParameters.translations[0],
      book_number: 0,
      chapter: 0,
      verse: 0,
      reference: strongCode,
      strong_code: strongCode,
    })
    setWindowState({ openedFor: response, views: [view] })
    loadView(view)
  }

  // A link inside a window: open another window on top of it, so Back can return.
  function openVerse(kind: ContextKind, target: VerseTarget) {
    const view = newView(kind, target)
    setWindowState((current) => (current ? { ...current, views: [...current.views, view] } : current))
    loadView(view)
  }

  function goBack() {
    contextRequest.current?.abort()
    setWindowState((current) =>
      current && current.views.length > 1 ? { ...current, views: current.views.slice(0, -1) } : current,
    )
  }

  // Switch Related Verses between "points to" and "pointed to by". The old list stays up until the
  // new one arrives.
  function changeDirection(direction: RelatedDirection) {
    if (currentView === null || currentView.direction === direction) {
      return
    }
    updateView(currentView.id, { direction, errorMessage: '' })
    loadView({ ...currentView, direction })
  }

  const closeContext = useCallback(() => {
    contextRequest.current?.abort()
    setWindowState(null)
    // Put the keyboard focus back on the link that was used, once the list is visible again.
    const trigger = contextTrigger.current
    window.setTimeout(() => trigger?.focus(), 0)
  }, [])

  useEffect(() => {
    if (!showContext) {
      return
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        closeContext()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [showContext, closeContext])

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
        {response && response.total === 0 && <p>No verses matched your search.</p>}

        <div hidden={showContext}>
          {response && response.total > 0 && (
            <div className="result-header">
              {sortColumns.map((column) => {
                if (isLicensed && column.field === 'text') {
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
                  {showTranslationCode && <span className="translation-code"> {result.translation}</span>}
                </span>
                <div className="verse-column">
                  <span className="verse-text">
                    {highlight(result.text, response.terms, searchParameters.wholeWords)}
                  </span>
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

        {showContext && windowState && currentView && (
          <ContextWindow
            key={currentView.id}
            view={currentView}
            canGoBack={windowState.views.length > 1}
            terms={windowState.views.length === 1 ? (response?.terms ?? []) : []}
            wholeWords={searchParameters.wholeWords}
            onBack={goBack}
            onClose={closeContext}
            onOpenVerse={openVerse}
            onChangeDirection={changeDirection}
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
