import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchBooks, fetchTranslations, searchBible } from './api'
import CopyrightPage from './CopyrightPage'
import SearchForm from './SearchForm'
import SearchResults from './SearchResults'
import type { Book, PerPage, SearchParameters, SearchResponse, SortField, Translation } from './types'
import './App.css'

// Row height and page chrome are rough guesses used for the first search; the results page
// measures the real rows and corrects the page size once they are on screen.
const estimatedRowHeight = 70
const estimatedHeightAboveList = 490

function estimateFitCount() {
  return Math.max(1, Math.floor((window.innerHeight - estimatedHeightAboveList) / estimatedRowHeight))
}

function App() {
  const [translations, setTranslations] = useState<Translation[]>([])
  const [books, setBooks] = useState<Book[]>([])
  const [loadErrorMessage, setLoadErrorMessage] = useState('')

  const [searchParameters, setSearchParameters] = useState<SearchParameters | null>(null)
  const [selectedBook, setSelectedBook] = useState<number | null>(null)
  const [perPage, setPerPage] = useState<PerPage>('automatic')
  const [isShowingCopyrights, setIsShowingCopyrights] = useState(false)
  const [response, setResponse] = useState<SearchResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [searchErrorMessage, setSearchErrorMessage] = useState('')
  const [fittedPerPage, setFittedPerPage] = useState(estimateFitCount)
  const activeRequest = useRef<AbortController | null>(null)

  useEffect(() => {
    Promise.all([fetchTranslations(), fetchBooks()])
      .then(([loadedTranslations, loadedBooks]) => {
        setTranslations(loadedTranslations)
        setBooks(loadedBooks)
      })
      .catch((error) =>
        setLoadErrorMessage(error instanceof Error ? error.message : 'Could not load Bible data'),
      )
  }, [])

  function runSearch(
    newSearchParameters: SearchParameters,
    newPage: number,
    newBook: number | null,
    fitCount = fittedPerPage,
  ) {
    activeRequest.current?.abort()
    const controller = new AbortController()
    activeRequest.current = controller

    setSearchParameters(newSearchParameters)
    setSelectedBook(newBook)
    setIsLoading(true)
    setSearchErrorMessage('')

    const perPage = newSearchParameters.perPage === 'automatic' ? fitCount : newSearchParameters.perPage
    searchBible(newSearchParameters, newPage, newBook, perPage, controller.signal)
      .then((searchResponse) => {
        setResponse(searchResponse)
        setIsLoading(false)
      })
      .catch((error) => {
        if (controller.signal.aborted) {
          return
        }
        setSearchErrorMessage(error instanceof Error ? error.message : 'Search failed')
        setIsLoading(false)
      })
  }

  function handleSearch(newSearchParameters: SearchParameters) {
    setResponse(null)
    runSearch(newSearchParameters, 1, null)
  }

  function handleSelectBook(book: number | null) {
    if (searchParameters) {
      runSearch(searchParameters, 1, book)
    }
  }

  function handleChangePage(newPage: number) {
    if (searchParameters) {
      runSearch(searchParameters, newPage, selectedBook)
    }
  }

  function handleSort(sortBy: SortField) {
    if (searchParameters) {
      const sortDirection =
        searchParameters.sortBy === sortBy && searchParameters.sortDirection === 'asc'
          ? 'desc'
          : 'asc'
      runSearch({ ...searchParameters, sortBy, sortDirection }, 1, selectedBook)
    }
  }

  function handleClearSort() {
    if (searchParameters) {
      runSearch({ ...searchParameters, sortBy: null, sortDirection: 'asc' }, 1, selectedBook)
    }
  }

  // Called by the results page once it knows how many rows fit in the window.
  const handleFit = useCallback(
    (fitCount: number) => {
      setFittedPerPage(fitCount)
      if (searchParameters) {
        runSearch(searchParameters, 1, selectedBook, fitCount)
      }
    },
    // runSearch only reads state that is already listed here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [searchParameters, selectedBook],
  )

  function handleChangePerPage(newPerPage: PerPage) {
    setPerPage(newPerPage)
    if (searchParameters) {
      runSearch({ ...searchParameters, perPage: newPerPage }, 1, selectedBook)
    }
  }

  return (
    <main className="app">
      <img className="site-logo" src="/logo.svg" alt="Bible and Beyond" />
      <nav className="tabs" aria-label="Sections">
        <span className="tab active">Search for specific words or phrases</span>
      </nav>

      {loadErrorMessage && <p className="error">{loadErrorMessage}</p>}
      {isShowingCopyrights && <CopyrightPage onBack={() => setIsShowingCopyrights(false)} />}
      {/* The search stays mounted while the copyright page is open, so nothing typed is lost. */}
      <div hidden={isShowingCopyrights}>
        {translations.length > 0 && (
          <SearchForm
            translations={translations}
            books={books}
            perPage={perPage}
            onChangePerPage={handleChangePerPage}
            onSearch={handleSearch}
          >
            {searchParameters !== null && (
              <SearchResults
                searchParameters={searchParameters}
                response={response}
                books={books}
                selectedBook={selectedBook}
                isLoading={isLoading}
                errorMessage={searchErrorMessage}
                onSelectBook={handleSelectBook}
                onChangePage={handleChangePage}
                onChangePerPage={handleChangePerPage}
                onFit={handleFit}
                onSort={handleSort}
                onClearSort={handleClearSort}
                onShowCopyrights={() => setIsShowingCopyrights(true)}
              />
            )}
          </SearchForm>
        )}
      </div>

      <footer className="site-footer">
        Scripture for the NIV, NASB and The Message is provided through{' '}
        <a href="https://api.bible" target="_blank" rel="noreferrer">
          API.Bible
        </a>
        .{' '}
        <button type="button" className="link-button" onClick={() => setIsShowingCopyrights(true)}>
          Bible copyright notices
        </button>
      </footer>
    </main>
  )
}

export default App
