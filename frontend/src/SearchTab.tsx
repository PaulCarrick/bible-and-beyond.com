import { useCallback, useRef, useState } from 'react'
import { searchBible, searchCommentaries } from './api'
import { chooseContextTranslation } from './contextTranslation'
import LicensedResults from './LicensedResults'
import ResultFilters from './ResultFilters'
import SearchForm from './SearchForm'
import SearchResults from './SearchResults'
import type {
  Book,
  CommentarySource,
  PerPage,
  SearchParameters,
  SearchResponse,
  SortField,
  Translation,
} from './types'

// Row height and page chrome are rough guesses used for the first search; the results page
// measures the real rows and corrects the page size once they are on screen.
const estimatedRowHeight = 70
const estimatedHeightAboveList = 490

function estimateFitCount() {
  return Math.max(1, Math.floor((window.innerHeight - estimatedHeightAboveList) / estimatedRowHeight))
}

export type SearchMode = 'bible' | 'commentary'

interface SearchTabProps {
  // Search the Bibles, or the text of the commentaries. Each tab keeps its own query and results.
  mode: SearchMode
  translations: Translation[]
  books: Book[]
  commentaries: CommentarySource[]
  isHidden: boolean
  onShowCopyrights: () => void
}

// The licensed Bibles (API.Bible) are searched one at a time, so when they are chosen with the Bibles on this site
// the main list searches the Bibles on this site and each licensed Bible gets a section of its own under it. When
// only licensed Bibles are chosen, the first is the main list.
function splitTranslations(searchParameters: SearchParameters, translations: Translation[]) {
  const isLicensed = (code: string) =>
    translations.some((translation) => translation.code === code && translation.source === 'api_bible')
  const local = searchParameters.translations.filter((code) => !isLicensed(code))
  const licensed = searchParameters.translations.filter(isLicensed)
  const main = local.length > 0 ? local : licensed.slice(0, 1)
  return {
    mainParameters: { ...searchParameters, translations: main },
    sectionCodes: local.length > 0 ? licensed : licensed.slice(1),
  }
}

function SearchTab({ mode, translations, books, commentaries, isHidden, onShowCopyrights }: SearchTabProps) {
  const [searchParameters, setSearchParameters] = useState<SearchParameters | null>(null)
  const [selectedBook, setSelectedBook] = useState<number | null>(null)
  const [perPage, setPerPage] = useState<PerPage>('automatic')
  const [response, setResponse] = useState<SearchResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [searchErrorMessage, setSearchErrorMessage] = useState('')
  const [fittedPerPage, setFittedPerPage] = useState(estimateFitCount)
  const activeRequest = useRef<AbortController | null>(null)

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

    const rowsPerPage = newSearchParameters.perPage === 'automatic' ? fitCount : newSearchParameters.perPage
    const search = mode === 'commentary' ? searchCommentaries : searchBible
    const mainParameters =
      mode === 'commentary' ? newSearchParameters : splitTranslations(newSearchParameters, translations).mainParameters
    search(mainParameters, newPage, newBook, rowsPerPage, controller.signal)
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
        searchParameters.sortBy === sortBy && searchParameters.sortDirection === 'asc' ? 'desc' : 'asc'
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

  // "Show in Context" under a commentary result needs a Bible to show.
  const contextTranslation = chooseContextTranslation(translations)
  const split =
    searchParameters !== null && mode === 'bible' ? splitTranslations(searchParameters, translations) : null
  return (
    // The search stays mounted while the other tab or the copyright page is open, so nothing typed is lost.
    <div hidden={isHidden}>
      {translations.length > 0 && (
        <SearchForm
          mode={mode}
          translations={translations}
          books={books}
          commentaries={commentaries}
          perPage={perPage}
          onChangePerPage={handleChangePerPage}
          onSearch={handleSearch}
          // Not for the licensed Bibles, whose results cannot be counted by book.
          filters={
            response !== null && response.source !== 'api_bible' ? (
              <ResultFilters
                books={books}
                bookCounts={response.book_counts}
                selectedBook={selectedBook}
                onSelectBook={handleSelectBook}
              />
            ) : null
          }
        >
          {searchParameters !== null && (
            <SearchResults
              mode={mode}
              contextTranslation={contextTranslation}
              searchParameters={split?.mainParameters ?? searchParameters}
              response={response}
              books={books}
              selectedBook={selectedBook}
              isLoading={isLoading}
              errorMessage={searchErrorMessage}
              onSelectBook={handleSelectBook}
              onChangePage={handleChangePage}
              onFit={handleFit}
              onSort={handleSort}
              onClearSort={handleClearSort}
              onShowCopyrights={onShowCopyrights}
            >
              {split?.sectionCodes.map((code) => (
                <LicensedResults
                  key={code}
                  code={code}
                  name={translations.find((translation) => translation.code === code)?.name ?? code}
                  searchParameters={searchParameters}
                  onShowCopyrights={onShowCopyrights}
                />
              ))}
            </SearchResults>
          )}
        </SearchForm>
      )}
    </div>
  )
}

export default SearchTab
