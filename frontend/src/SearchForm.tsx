import { useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { parsePerPage, perPageOptions } from './perPage'
import type { Book, MatchMode, PerPage, SearchParameters, Translation } from './types'

const bookGroups = [
  { name: 'Old Testament', bookStart: 1, bookEnd: 39 },
  { name: 'New Testament', bookStart: 40, bookEnd: 66 },
  { name: 'Law (Genesis–Deuteronomy)', bookStart: 1, bookEnd: 5 },
  { name: 'History (Joshua–Esther)', bookStart: 6, bookEnd: 17 },
  { name: 'Poetry (Job–Song of Solomon)', bookStart: 18, bookEnd: 22 },
  { name: 'Prophets (Isaiah–Malachi)', bookStart: 23, bookEnd: 39 },
  { name: 'Gospels and Acts', bookStart: 40, bookEnd: 44 },
  { name: 'Epistles (Romans–Jude)', bookStart: 45, bookEnd: 65 },
]

type Scope = 'entire' | 'group' | 'range'

interface SearchFormProps {
  translations: Translation[]
  books: Book[]
  perPage: PerPage
  onChangePerPage: (perPage: PerPage) => void
  onSearch: (searchParameters: SearchParameters) => void
  // The results, shown between the search box and the options.
  children: ReactNode
}

function SearchForm({
  translations,
  books,
  perPage,
  onChangePerPage,
  onSearch,
  children,
}: SearchFormProps) {
  const [query, setQuery] = useState('')
  const [matchMode, setMatchMode] = useState<MatchMode>('all')
  const [wholeWords, setWholeWords] = useState(false)
  const [selectedCodes, setSelectedCodes] = useState<string[]>(['BSB'])
  const [searchMultiple, setSearchMultiple] = useState(false)
  const [scope, setScope] = useState<Scope>('entire')
  const [groupIndex, setGroupIndex] = useState(0)
  const [rangeStart, setRangeStart] = useState(1)
  const [rangeEnd, setRangeEnd] = useState(66)

  function toggleCode(code: string) {
    setSelectedCodes((current) =>
      current.includes(code) ? current.filter((entry) => entry !== code) : [...current, code],
    )
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!canSearch) {
      return
    }
    let bookStart = 1
    let bookEnd = 66
    if (scope === 'group') {
      bookStart = bookGroups[groupIndex].bookStart
      bookEnd = bookGroups[groupIndex].bookEnd
    } else if (scope === 'range') {
      bookStart = Math.min(rangeStart, rangeEnd)
      bookEnd = Math.max(rangeStart, rangeEnd)
    }
    onSearch({
      query: query.trim(),
      matchMode: selectedIsLicensed ? 'all' : matchMode,
      wholeWords: selectedIsLicensed ? false : wholeWords,
      translations: selectedCodes,
      bookStart,
      bookEnd,
      perPage,
      sortBy: null,
      sortDirection: 'asc',
    })
  }

  const selectedIsLicensed = translations.some(
    (translation) => translation.source === 'api_bible' && selectedCodes.includes(translation.code),
  )
  const localTranslations = translations.filter((translation) => translation.source === 'local')
  const licensedTranslations = translations.filter((translation) => translation.source === 'api_bible')
  const canSearch = query.trim() !== '' && selectedCodes.length > 0

  return (
    <form className="search-form" onSubmit={handleSubmit}>
      <label className="field-label" htmlFor="search-query">
        Enter the words or phrases to search for
      </label>
      <div className="search-row">
        <input
          id="search-query"
          type="text"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder='Example "Jesus love"'
        />
        <button type="submit" className="primary-button" disabled={!canSearch}>
          Search for keyword or phrase
        </button>
      </div>

      {children}

      <details className="search-options">
        <summary>Search Options</summary>
        <div className="options-body">
          <div className="form-row">
            <select
              aria-label="Match mode"
              value={selectedIsLicensed ? 'all' : matchMode}
              disabled={selectedIsLicensed}
              onChange={(event) => setMatchMode(event.target.value as MatchMode)}
            >
              <option value="all">Match ALL words</option>
              <option value="any">Match ANY word</option>
              <option value="phrase">Match exact phrase</option>
            </select>
            <label className="inline-label">
              <input
                type="checkbox"
                checked={wholeWords && !selectedIsLicensed}
                disabled={selectedIsLicensed}
                onChange={(event) => setWholeWords(event.target.checked)}
              />
              Match whole words only
            </label>
          </div>

          <span className="field-label">Select Bibles to search</span>
          {searchMultiple ? (
            <div className="form-row">
              {localTranslations.map((translation) => (
                <label className="inline-label" key={translation.code}>
                  <input
                    type="checkbox"
                    checked={selectedCodes.includes(translation.code)}
                    onChange={() => toggleCode(translation.code)}
                  />
                  {translation.name} ({translation.code})
                </label>
              ))}
            </div>
          ) : (
            <select
              aria-label="Version"
              value={selectedCodes[0] ?? ''}
              onChange={(event) => setSelectedCodes([event.target.value])}
            >
              <optgroup label="Bibles on this site">
                {localTranslations.map((translation) => (
                  <option key={translation.code} value={translation.code}>
                    {translation.name} ({translation.code})
                  </option>
                ))}
              </optgroup>
              <optgroup label="Licensed Bibles (via API.Bible)">
                {licensedTranslations.map((translation) => (
                  <option key={translation.code} value={translation.code}>
                    {translation.name} ({translation.code})
                  </option>
                ))}
              </optgroup>
            </select>
          )}
          {selectedIsLicensed ? (
            <p className="option-note">
              Licensed Bibles are searched one at a time. They match all of the words, in Bible order,
              and do not offer match any, exact phrase, whole words or sorting by contents.
            </p>
          ) : (
            <button
              type="button"
              className="link-button"
              onClick={() => {
                if (searchMultiple) {
                  setSelectedCodes((current) => current.slice(0, 1))
                }
                setSearchMultiple(!searchMultiple)
              }}
            >
              {searchMultiple ? 'Search in a single version' : 'Search in multiple versions'}
            </button>
          )}

          <label className="inline-label">
            <input
              type="radio"
              name="scope"
              checked={scope === 'entire'}
              onChange={() => setScope('entire')}
            />
            Search the entire Bible(s)
          </label>
          <div className="form-row">
            <label className="inline-label">
              <input
                type="radio"
                name="scope"
                checked={scope === 'group'}
                onChange={() => setScope('group')}
              />
              Limit the search to
            </label>
            <select
              aria-label="Limit the search to"
              disabled={scope !== 'group'}
              value={groupIndex}
              onChange={(event) => setGroupIndex(Number(event.target.value))}
            >
              {bookGroups.map((group, index) => (
                <option key={group.name} value={index}>
                  {group.name}
                </option>
              ))}
            </select>
          </div>
          <div className="form-row">
            <label className="inline-label">
              <input
                type="radio"
                name="scope"
                checked={scope === 'range'}
                onChange={() => setScope('range')}
              />
              Search by books
            </label>
            <select
              aria-label="First book"
              disabled={scope !== 'range'}
              value={rangeStart}
              onChange={(event) => setRangeStart(Number(event.target.value))}
            >
              {books.map((book) => (
                <option key={book.number} value={book.number}>
                  {book.name}
                </option>
              ))}
            </select>
            to
            <select
              aria-label="Last book"
              disabled={scope !== 'range'}
              value={rangeEnd}
              onChange={(event) => setRangeEnd(Number(event.target.value))}
            >
              {books.map((book) => (
                <option key={book.number} value={book.number}>
                  {book.name}
                </option>
              ))}
            </select>
          </div>

          <label className="inline-label">
            Display
            <select
              value={perPage}
              onChange={(event) => onChangePerPage(parsePerPage(event.target.value))}
            >
              {perPageOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            Results per page
          </label>
        </div>
      </details>
    </form>
  )
}

export default SearchForm
