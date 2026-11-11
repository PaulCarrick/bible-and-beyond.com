import { useContext, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { AccountContext } from './AccountContext'
import { parsePerPage, perPageOptions } from './perPage'
import type { Book, CommentarySource, PerPage, SearchMatchMode, SearchParameters, Translation } from './types'

const bookGroups = [
  { name: 'Old Testament', bookStart: 1, bookEnd: 39 },
  { name: 'New Testament', bookStart: 40, bookEnd: 66 },
  { name: 'Law (Genesis–Deuteronomy)', bookStart: 1, bookEnd: 5 },
  { name: 'History (Joshua–Esther)', bookStart: 6, bookEnd: 17 },
  { name: 'Poetry (Job–Song of Solomon)', bookStart: 18, bookEnd: 22 },
  { name: 'Prophets (Isaiah–Malachi)', bookStart: 23, bookEnd: 39 },
  { name: 'Gospels and Acts', bookStart: 40, bookEnd: 44 },
  { name: 'Epistles (Romans–Jude)', bookStart: 45, bookEnd: 65 },
  // Paul's thirteen letters; Hebrews (58), whose author is not named, is left out.
  { name: 'Pauline Epistles (Romans–Philemon)', bookStart: 45, bookEnd: 57 },
]

type Scope = 'entire' | 'group' | 'range'

interface SearchFormProps {
  // Search the Bibles, or the text of the commentaries.
  mode: 'bible' | 'commentary'
  commentaries: CommentarySource[]
  translations: Translation[]
  books: Book[]
  perPage: PerPage
  onChangePerPage: (perPage: PerPage) => void
  onSearch: (searchParameters: SearchParameters) => void
  // The results, shown between the search box and the options.
  children: ReactNode
  // The filters of the results (which book to keep), shown in the options. None until there are results.
  filters?: ReactNode
}

function SearchForm({
  mode,
  commentaries,
  translations,
  books,
  perPage,
  onChangePerPage,
  onSearch,
  children,
  filters,
}: SearchFormProps) {
  const { user } = useContext(AccountContext)
  const [query, setQuery] = useState('')
  const [matchMode, setMatchMode] = useState<SearchMatchMode>('all')
  const [wholeWords, setWholeWords] = useState(false)
  const [selectedCodes, setSelectedCodes] = useState<string[]>(['BSB'])
  // Which commentary to search; empty means all of them.
  const [commentary, setCommentary] = useState('')
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
    const isCommentarySearch = mode === 'commentary'
    onSearch({
      query: query.trim(),
      matchMode: effectiveMatchMode,
      wholeWords: onlyLicensed || isCommentarySearch || isAiSearch ? false : wholeWords,
      translations: isCommentarySearch ? [] : selectedCodes,
      commentary: isCommentarySearch && commentary !== '' ? commentary : null,
      bookStart,
      bookEnd,
      perPage,
      sortBy: null,
      sortDirection: 'asc',
    })
  }

  const licensedCodes = translations
    .filter((translation) => translation.source === 'api_bible')
    .map((translation) => translation.code)
  const selectedLicensed = selectedCodes.filter((code) => licensedCodes.includes(code))
  // The match options apply only to the Bibles on this site; the licensed ones always match all of the words.
  const onlyLicensed = selectedCodes.length > 0 && selectedLicensed.length === selectedCodes.length
  const localTranslations = translations.filter((translation) => translation.source === 'local')
  const licensedTranslations = translations.filter((translation) => translation.source === 'api_bible')
  const isCommentarySearch = mode === 'commentary'
  const queryId = isCommentarySearch ? 'search-query-commentary' : 'search-query'
  const canSearch = query.trim() !== '' && (isCommentarySearch || selectedCodes.length > 0)
  // "Use AI" is only for the Bible search and a logged-in account an administrator allowed (the server checks too).
  const canUseAi = !isCommentarySearch && user?.open_ai_queries === true
  // The licensed Bibles always match all of the words; AI goes back to it if the visitor logs out.
  const effectiveMatchMode: SearchMatchMode =
    onlyLicensed && !isCommentarySearch ? 'all' : matchMode === 'ai' && !canUseAi ? 'all' : matchMode
  const isAiSearch = effectiveMatchMode === 'ai'

  return (
    <form className="search-form" onSubmit={handleSubmit}>
      <label className="field-label" htmlFor={queryId}>
        Enter the words or phrases to search for
      </label>
      <div className="search-row">
        <input
          id={queryId}
          type="text"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={
            isCommentarySearch
              ? 'Example "born again" or charity'
              : isAiSearch
                ? 'Example: comfort when someone has died'
                : 'Example "Jesus love" or G0025'
          }
        />
        <button type="submit" className="primary-button" disabled={!canSearch}>
          {isCommentarySearch ? 'Search the commentaries' : isAiSearch ? 'Find verses with AI' : 'Search for keyword or phrase'}
        </button>
      </div>

      {children}

      <details className="search-options">
        <summary>Search Options</summary>
        <div className="options-body">
          <div className="form-row">
            <select
              aria-label="Match mode"
              value={effectiveMatchMode}
              disabled={onlyLicensed && !isCommentarySearch}
              onChange={(event) => setMatchMode(event.target.value as SearchMatchMode)}
            >
              <option value="all">Match ALL words</option>
              <option value="any">Match ANY word</option>
              <option value="phrase">Match exact phrase</option>
              {canUseAi && <option value="ai">Use AI to find related verses</option>}
            </select>
            {!isCommentarySearch && (
              <label className="inline-label">
                <input
                  type="checkbox"
                  checked={wholeWords && !onlyLicensed && !isAiSearch}
                  disabled={onlyLicensed || isAiSearch}
                  onChange={(event) => setWholeWords(event.target.checked)}
                />
                Match whole words only
              </label>
            )}
          </div>
          {isAiSearch && (
            <p className="option-note">
              An AI (Google's Gemini) suggests up to 30 verses related to what you type, and they are listed from
              the Bibles on this site, in Bible order. The AI can be wrong, so read each verse in context. The
              licensed Bibles (NIV, NASB, The Message) are not searched this way.
            </p>
          )}
          {isCommentarySearch && (
            <p className="option-note">
              Words match in any form, so love also finds loved and loving. Every word counts, even small
              ones such as the and of, so an exact phrase finds just that wording. Notes are listed best
              match first.
            </p>
          )}

          {isCommentarySearch ? (
            <>
          <span className="field-label">Select a commentary to search</span>
          <select
            aria-label="Commentary"
            value={commentary}
            onChange={(event) => setCommentary(event.target.value)}
          >
            <option value="">All commentaries</option>
            {commentaries.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.name}
              </option>
            ))}
          </select>

            </>
          ) : (
            <>
          <span className="field-label">Select Bibles to search</span>
          {searchMultiple ? (
            <>
              <span className="option-group-label">Bibles on this site</span>
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
              {licensedTranslations.length > 0 && (
                <>
                  <span className="option-group-label">Licensed Bibles (via API.Bible)</span>
                  <div className="form-row">
                    {licensedTranslations.map((translation) => (
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
                </>
              )}
            </>
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
          {selectedLicensed.length > 0 && (
            <p className="option-note">
              {isAiSearch
                ? 'An AI search lists only the Bibles on this site; the licensed Bibles are left out.'
                : onlyLicensed
                ? 'Licensed Bibles match all of the words, in Bible order, and do not offer match any, exact phrase, whole words, the book filters or sorting by contents.'
                : 'The licensed Bibles are listed after the Bibles on this site, each in its own section. They match all of the words, in Bible order; match any, exact phrase, whole words, the book filters and sorting apply only to the Bibles on this site.'}
              {onlyLicensed && selectedLicensed.length > 1 && ' Each is listed in its own section.'}
            </p>
          )}
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

            </>
          )}
          <label className="inline-label">
            <input
              type="radio"
              name="scope"
              checked={scope === 'entire'}
              onChange={() => setScope('entire')}
            />
            {isCommentarySearch ? 'Search the entire Bible' : 'Search the entire Bible(s)'}
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

          {filters}
        </div>
      </details>
    </form>
  )
}

export default SearchForm
