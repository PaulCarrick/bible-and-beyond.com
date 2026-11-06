import type { Book, Copyright, SearchParameters, SearchResponse, Translation } from './types'

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
