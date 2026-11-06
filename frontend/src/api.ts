import type {
  Book,
  ContextKind,
  Copyright,
  ParallelVerse,
  LexiconEntry,
  OriginalWordsResponse,
  RelatedDirection,
  RelatedResponse,
  SearchParameters,
  SearchResponse,
  Translation,
  VerseContext,
} from './types'

const mlServiceUrl = import.meta.env.VITE_ML_SERVICE_URL ?? 'http://localhost:8000'

const tooManyRequestsMessage =
  "You're searching too quickly. Please wait a few seconds and try again."
const serverErrorMessage =
  'The search service is not available right now. Please try again in a moment.'

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    // The web server answers a visitor who is over the rate limit with a plain page, not JSON.
    if (response.status === 429) {
      throw new Error(tooManyRequestsMessage)
    }
    let message =
      response.status >= 500 ? serverErrorMessage : `Request failed with status ${response.status}`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') {
        message = body.detail
      }
    } catch {
      // The response had no JSON body; keep the status message.
    }
    throw new Error(message)
  }
  return response.json()
}

export async function fetchTranslations(): Promise<Translation[]> {
  return readJson(await fetch(`${mlServiceUrl}/translations`))
}

// Show in Context: the verses around one verse. How many come before and after is set by an
// administrator. Full Chapter: every verse of the chapter that contains the verse.
export async function fetchContext(
  kind: Extract<ContextKind, 'context' | 'chapter'>,
  translation: string,
  book: number,
  chapter: number,
  verse: number,
  signal: AbortSignal,
): Promise<VerseContext> {
  const queryString = new URLSearchParams({
    translation,
    book: String(book),
    chapter: String(chapter),
    verse: String(verse),
  })
  const path = kind === 'chapter' ? 'chapter' : 'context'
  return readJson(await fetch(`${mlServiceUrl}/${path}?${queryString}`, { signal }))
}

// Other Translations: the same verse in every Bible stored on this site.
export async function fetchParallel(
  book: number,
  chapter: number,
  verse: number,
  signal: AbortSignal,
): Promise<ParallelVerse> {
  const queryString = new URLSearchParams({
    book: String(book),
    chapter: String(chapter),
    verse: String(verse),
  })
  return readJson(await fetch(`${mlServiceUrl}/parallel?${queryString}`, { signal }))
}

// Related Verses: the verses that Bible readers have linked to this one (cross references).
export async function fetchRelated(
  translation: string,
  book: number,
  chapter: number,
  verse: number,
  direction: RelatedDirection,
  signal: AbortSignal,
): Promise<RelatedResponse> {
  const queryString = new URLSearchParams({
    translation,
    book: String(book),
    chapter: String(chapter),
    verse: String(verse),
    direction,
  })
  return readJson(await fetch(`${mlServiceUrl}/related?${queryString}`, { signal }))
}

// Original Words: the Hebrew or Greek words of a verse (STEPBible data).
export async function fetchOriginalWords(
  book: number,
  chapter: number,
  verse: number,
  signal: AbortSignal,
): Promise<OriginalWordsResponse> {
  const queryString = new URLSearchParams({
    book: String(book),
    chapter: String(chapter),
    verse: String(verse),
  })
  return readJson(await fetch(`${mlServiceUrl}/original-words?${queryString}`, { signal }))
}

// A lexicon entry for a Strong's number, with verses that use the word shown in one Bible.
export async function fetchLexiconEntry(
  translation: string,
  strongCode: string,
  signal: AbortSignal,
): Promise<LexiconEntry> {
  const queryString = new URLSearchParams({ translation, strong_code: strongCode })
  return readJson(await fetch(`${mlServiceUrl}/lexicon?${queryString}`, { signal }))
}

export async function fetchCopyrights(): Promise<Copyright[]> {
  return readJson(await fetch(`${mlServiceUrl}/copyrights`))
}

export async function fetchBooks(): Promise<Book[]> {
  return readJson(await fetch(`${mlServiceUrl}/books`))
}

export async function searchBible(
  searchParameters: SearchParameters,
  page: number,
  book: number | null,
  perPage: number,
  signal: AbortSignal,
): Promise<SearchResponse> {
  const queryString = new URLSearchParams({
    query: searchParameters.query,
    match_mode: searchParameters.matchMode,
    whole_words: String(searchParameters.wholeWords),
    book_start: String(searchParameters.bookStart),
    book_end: String(searchParameters.bookEnd),
    page: String(page),
    per_page: String(perPage),
  })
  for (const code of searchParameters.translations) {
    queryString.append('translations', code)
  }
  if (book !== null) {
    queryString.set('book', String(book))
  }
  if (searchParameters.sortBy !== null) {
    queryString.set('sort_by', searchParameters.sortBy)
    queryString.set('sort_direction', searchParameters.sortDirection)
  }
  return readJson(await fetch(`${mlServiceUrl}/search?${queryString}`, { signal }))
}
