import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import ContextWindow from './ContextWindow'
import { reportView } from './fums'
import { highlight, renderExcerpt } from './highlight'
import { useVerseWindows } from './useVerseWindows'
import { verseButtonProps } from './verseAddress'
import type { VerseInBible } from './verseAddress'
import type {
  Book,
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
  searchParameters: SearchParameters
  response: SearchResponse | null
  books: Book[]
  selectedBook: number | null
  isLoading: boolean
  errorMessage: string
  onSelectBook: (book: number | null) => void
  onChangePage: (page: number) => void
  onFit: (fitCount: number) => void
  onSort: (sortBy: SortField) => void
  onClearSort: () => void
  onShowCopyrights: () => void
  // Shown under the results and hidden with them while a window is open: the licensed Bibles' own sections.
  children?: ReactNode
}

function SearchResults({
  mode,
  contextTranslation,
  searchParameters,
  response,
  books,
  selectedBook,
  isLoading,
  errorMessage,
  onSelectBook,
  onChangePage,
  onFit,
  onSort,
  onClearSort,
  onShowCopyrights,
  children,
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
  // Where a result's verse is, for opening it in a new tab (a commentary result uses the Bible chosen for that).
  function verseOf(result: SearchResult): VerseInBible {
    return {
      translation: response?.source === 'commentary' ? contextTranslation : result.translation,
      book: result.book_number,
      chapter: result.chapter,
      verse: result.verse,
    }
  }

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

  const hasHeaderRow = response !== null && response.total > 0
  const pageCount = response ? Math.max(1, Math.ceil(response.total / response.per_page)) : 1
  const showTranslationCode = searchParameters.translations.length > 1

  return (
    <div className="results-layout">
      <div className={hasHeaderRow ? 'results-main panel has-header-row' : 'results-main panel'}>
        {/* The count line is also in the header row of the list (at its right end) when there is one. This one
            is for the other times: while searching, with no results, or on a phone, where that row is not shown. */}
        <div className={hasHeaderRow && !response?.strong && !response?.ai ? 'results-heading is-folded' : 'results-heading'}>
          <p className="results-summary-standalone">
            <strong>
              {response ? response.total.toLocaleString() : '…'}{' '}
              {mode === 'commentary' ? 'commentary results' : 'Bible results'}
            </strong>
            {selectedBook !== null && (
              <>
                {' '}
                · only {books.find((book) => book.number === selectedBook)?.name ?? 'one book'}{' '}
                <button type="button" className="link-button" onClick={() => onSelectBook(null)}>
                  Show all books
                </button>
              </>
            )}
          </p>
          {response?.ai && (
            <p className="strong-note">
              Verses an AI (Google&rsquo;s Gemini) suggested for &ldquo;{response.query}&rdquo;, in Bible order. The AI
              can be wrong, so read each verse in context.
            </p>
          )}
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
          <p>
            {mode === 'commentary'
              ? 'No commentary notes matched your search.'
              : response.ai
                ? 'The AI did not suggest any verses for this. Try describing it in other words.'
                : 'No verses matched your search.'}
          </p>
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
              <p className="results-summary">
                <strong>
                  {response ? response.total.toLocaleString() : '…'}{' '}
                  {mode === 'commentary' ? 'commentary results' : 'Bible results'}
                </strong>
                {selectedBook !== null && (
                  <>
                    {' '}
                    · only {books.find((book) => book.number === selectedBook)?.name ?? 'one book'}{' '}
                    <button type="button" className="link-button" onClick={() => onSelectBook(null)}>
                      Show all books
                    </button>
                  </>
                )}
              </p>
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
                        {...verseButtonProps(verseOf(result), (element) => openContext('context', result, element))}
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
                        {...verseButtonProps(verseOf(result), (element) => openContext('context', result, element))}
                      >
                        Show in Context
                        <span className="visually-hidden"> for {result.reference}</span>
                      </button>
                      <button
                        type="button"
                        className="link-button context-link"
                        {...verseButtonProps(verseOf(result), (element) => openContext('chapter', result, element))}
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

          {children}
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

    </div>
  )
}

export default SearchResults
