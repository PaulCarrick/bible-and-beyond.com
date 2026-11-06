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

export type ContextKind = 'context' | 'chapter' | 'parallel' | 'related'

// A verse that a window is about, named well enough to ask for more about it.
export interface VerseTarget {
  translation: string
  book_number: number
  chapter: number
  verse: number
  reference: string
}

// Related Verses can look two ways: where the verse points to, and which verses point at it.
export type RelatedDirection = 'from' | 'to'

export interface RelatedVerse {
  book_name: string
  chapter: number
  verse: number
  text: string
}

// One cross reference: a verse, or a range of verses, with its text in the Bible that was searched.
export interface RelatedReference {
  votes: number
  reference: string
  book_number: number
  chapter: number
  verse: number
  verses: RelatedVerse[]
  has_more_verses: boolean
}

// The best-voted cross references of one verse (the number shown is set by an administrator).
export interface RelatedResponse {
  translation: string
  book_number: number
  book_name: string
  chapter: number
  verse: number
  direction: RelatedDirection
  outgoing_total: number
  incoming_total: number
  total: number
  shown: number
  references: RelatedReference[]
}

export interface ParallelTranslation {
  code: string
  name: string
  language: string
  text: string
}

// One verse as it reads in each Bible stored on this site.
export interface ParallelVerse {
  book_number: number
  book_name: string
  chapter: number
  verse: number
  translations: ParallelTranslation[]
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
