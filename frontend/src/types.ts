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
