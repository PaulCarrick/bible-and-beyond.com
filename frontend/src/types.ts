export type MatchMode = 'all' | 'any' | 'phrase'
export type SortField = 'verse' | 'text'
export type SortDirection = 'asc' | 'desc'
export type PerPage = number | 'automatic'

export type TranslationSource = 'local' | 'api_bible'

export interface Translation {
  code: string
  name: string
  source: TranslationSource
}

export interface Copyright {
  code: string
  name: string
  abbreviation: string
  copyright: string
  rights_holder_url: string | null
}

export interface Book {
  number: number
  name: string
  testament: 'OT' | 'NT'
}

export interface SearchParameters {
  query: string
  matchMode: MatchMode
  wholeWords: boolean
  translations: string[]
  bookStart: number
  bookEnd: number
  perPage: PerPage
  sortBy: SortField | null
  sortDirection: SortDirection
}

export interface SearchResult {
  translation: string
  book_number: number
  book_name: string
  chapter: number
  verse: number
  reference: string
  text: string
}

export interface BookCount {
  book_number: number
  count: number
}

export interface ContextVerse {
  chapter: number
  verse: number
  text: string
  is_target: boolean
}

export interface VerseContext {
  translation: string
  book_number: number
  book_name: string
  chapter: number
  verse: number
  // Only in the answer for Show in Context, not for Full Chapter.
  verses_before?: number
  verses_after?: number
  verses: ContextVerse[]
}

export type ContextKind = 'context' | 'chapter'

export interface SearchResponse {
  source: TranslationSource
  fums_token?: string | null
  copyright?: string
  query: string
  terms: string[]
  total: number
  page: number
  per_page: number
  book_counts: BookCount[]
  results: SearchResult[]
}
