import { useEffect, useState } from 'react'
import { searchBible } from './api'
import { reportView } from './fums'
import { highlight } from './highlight'
import type { SearchParameters, SearchResponse } from './types'

// How many verses a section shows at once when the page size is "fit the screen": the sections sit under the
// main results, so they are kept short. Each page is one API.Bible request.
const automaticPerPage = 10

interface LicensedResultsProps {
  // The licensed Bible (NIV, NASB, MSG) and its name.
  code: string
  name: string
  searchParameters: SearchParameters
  onShowCopyrights: () => void
}

// The results of one licensed Bible (from API.Bible), shown under the results of the Bibles on this site when
// both kinds are searched at once. API.Bible searches one Bible at a time and pages its own results, so each
// licensed Bible has its own section, count and pages. It always matches all of the words in Bible order, and
// its verses have no links (Show in Context and the rest need the text stored here). Its copyright notice is
// shown with it and each page shown is reported to API.Bible (FUMS), as its terms ask.
function LicensedResults({ code, name, searchParameters, onShowCopyrights }: LicensedResultsProps) {
  const [response, setResponse] = useState<SearchResponse | null>(null)
  const [page, setPage] = useState(1)
  const [isLoading, setIsLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')

  const { query, bookStart, bookEnd } = searchParameters
  const perPage = searchParameters.perPage === 'automatic' ? automaticPerPage : searchParameters.perPage
  // A new search starts again at page 1. Sorting, the book filters and the match options of the main results
  // do not apply here, so changing them costs no API.Bible request.
  const searchKey = JSON.stringify([code, query, bookStart, bookEnd, perPage])
  const [shownSearchKey, setShownSearchKey] = useState(searchKey)
  if (shownSearchKey !== searchKey) {
    setShownSearchKey(searchKey)
    setPage(1)
  }

  useEffect(() => {
    const controller = new AbortController()
    const licensedParameters: SearchParameters = {
      query,
      matchMode: 'all',
      wholeWords: false,
      translations: [code],
      commentary: null,
      bookStart,
      bookEnd,
      perPage,
      sortBy: null,
      sortDirection: 'asc',
    }
    // Loading state for the request that starts here.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsLoading(true)
    setErrorMessage('')
    searchBible(licensedParameters, page, null, perPage, controller.signal)
      .then((searchResponse) => {
        setResponse(searchResponse)
        setIsLoading(false)
        if (searchResponse.fums_token) {
          reportView(searchResponse.fums_token)
        }
      })
      .catch((error) => {
        if (controller.signal.aborted) {
          return
        }
        setResponse(null)
        setErrorMessage(error instanceof Error ? error.message : 'Search failed')
        setIsLoading(false)
      })
    return () => controller.abort()
  }, [code, query, bookStart, bookEnd, perPage, page])

  const pageCount = response ? Math.max(1, Math.ceil(response.total / response.per_page)) : 1
  const headingId = `licensed-results-${code}`

  return (
    <section className="licensed-results" aria-labelledby={headingId}>
      <h3 id={headingId}>
        {name} ({code}): {response ? `${response.total.toLocaleString()} results` : isLoading ? 'searching…' : ''}
      </h3>
      {errorMessage && <p className="error">{errorMessage}</p>}
      {response && response.total === 0 && <p>No verses matched your search.</p>}

      {response && response.total > 0 && (
        <>
          <ol className={isLoading ? 'result-list is-loading' : 'result-list'}>
            {response.results.map((result) => (
              <li className="result" key={`${result.book_number}-${result.chapter}-${result.verse}`}>
                <span className="reference">{result.reference}</span>
                <div className="verse-column">
                  <span className="verse-text">{highlight(result.text, response.terms, false)}</span>
                </div>
              </li>
            ))}
          </ol>

          {response.copyright && (
            <p className="citation">
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

          {pageCount > 1 && (
            <nav className="pagination" aria-label={`${code} result pages`}>
              <button type="button" disabled={isLoading || response.page <= 1} onClick={() => setPage(1)}>
                First
              </button>
              <button type="button" disabled={isLoading || response.page <= 1} onClick={() => setPage(response.page - 1)}>
                Previous
              </button>
              <span>
                Page {response.page} of {pageCount}
              </span>
              <button
                type="button"
                disabled={isLoading || response.page >= pageCount}
                onClick={() => setPage(response.page + 1)}
              >
                Next
              </button>
              <button
                type="button"
                disabled={isLoading || response.page >= pageCount}
                onClick={() => setPage(pageCount)}
              >
                Last
              </button>
            </nav>
          )}
        </>
      )}
    </section>
  )
}

export default LicensedResults
