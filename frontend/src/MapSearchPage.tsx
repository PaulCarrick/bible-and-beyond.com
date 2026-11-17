import { useContext, useId, useRef, useState } from 'react'
import { AccountContext } from './AccountContext'
import type { FormEvent } from 'react'
import { mapFileAddress, searchMaps } from './api'
import type { MapSearchResponse } from './api'
import { renderExcerpt } from './highlight'
import { mapItem } from './listItems'
import { useListPicks } from './listPicks'
import ListSaveBox from './ListSaveBox'
import ListTick from './ListTick'
import MapsCredit from './MapsCredit'

interface MapSearchPageProps {
  isHidden: boolean
  // Show a map on the maps page.
  onOpen: (mapId: string) => void
}

type MatchMode = 'all' | 'any' | 'phrase'

interface Search {
  query: string
  matchMode: MatchMode
  page: number
  perPage: number
}

const perPage = 25

// Search the maps' titles, keywords, descriptions, verses and sources: words in any form, all of them, any of them
// or an exact phrase. A verse typed in ("Acts 13:4") also finds the maps that go with it, first. The page stays
// mounted, so the search and its results are kept while another page is open.
function MapSearchPage({ isHidden, onOpen }: MapSearchPageProps) {
  const queryId = useId()
  const [query, setQuery] = useState('')
  // Maps ticked for a list (My lists).
  const listPicks = useListPicks()
  const { user: listMember } = useContext(AccountContext)
  const [matchMode, setMatchMode] = useState<MatchMode>('all')
  const [response, setResponse] = useState<MapSearchResponse | null>(null)
  const [shown, setShown] = useState<Search | null>(null)
  const [isSearching, setIsSearching] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const controller = useRef<AbortController | null>(null)

  async function run(search: Search) {
    controller.current?.abort()
    const request = new AbortController()
    controller.current = request
    setIsSearching(true)
    setErrorMessage('')
    try {
      const found = await searchMaps(search, request.signal)
      if (!request.signal.aborted) {
        setResponse(found)
        setShown(search)
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

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (query.trim() !== '') {
      run({ query: query.trim(), matchMode, page: 1, perPage })
    }
  }

  const pageCount = response ? Math.max(1, Math.ceil(response.total / response.per_page)) : 1

  return (
    <div className="welcome book-search" hidden={isHidden}>
      <h1>Search the maps</h1>
      <p>
        Find a map by its title, its description, its keywords or a verse it goes with (type a verse such as{' '}
        <em>Acts 13:4</em>). Words are found in any form; put a phrase in quotation marks to keep it together.
      </p>

      <form className="book-search-form" onSubmit={handleSubmit}>
        <label htmlFor={queryId} className="visually-hidden">
          Words to search for
        </label>
        <div className="search-row">
          <input id={queryId} type="text" value={query} onChange={(event) => setQuery(event.target.value)} placeholder='Example "Paul" journey or Acts 13:4' />
          <button type="submit" className="primary-button" disabled={query.trim() === '' || isSearching}>
            Search the maps
          </button>
        </div>
        <div className="book-search-options">
          <label>
            Match{' '}
            <select value={matchMode} onChange={(event) => setMatchMode(event.target.value as MatchMode)}>
              <option value="all">All the words</option>
              <option value="any">Any of the words</option>
              <option value="phrase">The exact phrase</option>
            </select>
          </label>
        </div>
      </form>

      <div>
        {errorMessage && <p className="error">{errorMessage}</p>}
        {isSearching && !response && <p>Searching…</p>}
        {response && (
          <>
            <p className="book-search-count">
              {response.total === 0 ? 'Nothing was found.' : `${response.total.toLocaleString()} ${response.total === 1 ? 'map' : 'maps'} found`}
            </p>
            <ul className={`result-list book-results${isSearching ? ' is-loading' : ''}`}>
              {response.results.map((result) => (
                <li key={result.id} className={listMember ? 'result book-result map-search-result has-list-tick' : 'result book-result map-search-result'}>
                  <img className="map-search-picture" src={mapFileAddress(result, 'thumbnail')} alt="" loading="lazy" />
                  <div>
                    <div className="book-result-place">
                      <strong>{result.title}</strong>
                      {result.verses_text ? ` · ${result.verses_text}` : ''}
                    </div>
                    <p className="book-result-text">{renderExcerpt(result.text)}</p>
                    <button type="button" className="link-button" onClick={() => onOpen(result.id)}>
                      Open this map
                    </button>
                  </div>
                  <ListTick item={mapItem(result)} picks={listPicks} />
                </li>
              ))}
            </ul>
            <ListSaveBox picks={listPicks} />
            {pageCount > 1 && shown && (
              <nav className="pagination" aria-label="Result pages">
                <button type="button" disabled={response.page <= 1 || isSearching} onClick={() => run({ ...shown, page: response.page - 1 })}>
                  Previous
                </button>
                <span>
                  Page {response.page} of {pageCount}
                </span>
                <button type="button" disabled={response.page >= pageCount || isSearching} onClick={() => run({ ...shown, page: response.page + 1 })}>
                  Next
                </button>
              </nav>
            )}
          </>
        )}
      </div>
      <p className="maps-credit">
        <MapsCredit />
      </p>
    </div>
  )
}

export default MapSearchPage
