import type {
  BibleChapter,
  BibleContents,
  CommentaryChapter,
  DevotionalContents,
  DevotionalSubscription,
  DevotionalInfo,
  DevotionalUnit,
  CommentaryContents,
  CommentaryResponse,
  CommentarySource,
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
  SiteSettings,
  AccountUser,
  NewAccount,
  Note,
  NotePage,
  NoteSubject,
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

// Commentaries: public-domain commentary notes on a verse (the first one that has notes unless one is named).
export async function fetchCommentaries(
  book: number,
  chapter: number,
  verse: number,
  commentary: string | null,
  signal: AbortSignal,
): Promise<CommentaryResponse> {
  const queryString = new URLSearchParams({
    book: String(book),
    chapter: String(chapter),
    verse: String(verse),
  })
  if (commentary) {
    queryString.set('commentary', commentary)
  }
  return readJson(await fetch(`${mlServiceUrl}/commentaries?${queryString}`, { signal }))
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
  // An AI search needs the login cookie (locally the page and the API are on different addresses).
  const credentials = searchParameters.matchMode === 'ai' ? 'include' : 'same-origin'
  return readJson(await fetch(`${mlServiceUrl}/search?${queryString}`, { signal, credentials }))
}

export async function fetchCommentarySources(): Promise<CommentarySource[]> {
  return readJson(await fetch(`${mlServiceUrl}/commentary-list`))
}

// Search inside the commentaries. Notes come back best match first, or in Bible order.
export async function searchCommentaries(
  searchParameters: SearchParameters,
  page: number,
  book: number | null,
  perPage: number,
  signal: AbortSignal,
): Promise<SearchResponse> {
  const queryString = new URLSearchParams({
    query: searchParameters.query,
    match_mode: searchParameters.matchMode,
    book_start: String(searchParameters.bookStart),
    book_end: String(searchParameters.bookEnd),
    page: String(page),
    per_page: String(perPage),
  })
  if (searchParameters.commentary !== null) {
    queryString.set('commentary', searchParameters.commentary)
  }
  if (book !== null) {
    queryString.set('book', String(book))
  }
  if (searchParameters.sortBy === 'verse') {
    queryString.set('sort_by', 'verse')
    queryString.set('sort_direction', searchParameters.sortDirection)
  }
  return readJson(await fetch(`${mlServiceUrl}/search-commentaries?${queryString}`, { signal }))
}

export async function fetchCommentaryContents(commentary: string, signal: AbortSignal): Promise<CommentaryContents> {
  const queryString = new URLSearchParams({ commentary })
  return readJson(await fetch(`${mlServiceUrl}/commentary-contents?${queryString}`, { signal }))
}

export async function fetchCommentaryChapter(
  commentary: string,
  book: number,
  chapter: number,
  signal: AbortSignal,
): Promise<CommentaryChapter> {
  const queryString = new URLSearchParams({ commentary, book: String(book), chapter: String(chapter) })
  return readJson(await fetch(`${mlServiceUrl}/commentary-chapter?${queryString}`, { signal }))
}

export async function fetchBibleContents(translation: string, signal: AbortSignal): Promise<BibleContents> {
  const queryString = new URLSearchParams({ translation })
  return readJson(await fetch(`${mlServiceUrl}/bible-contents?${queryString}`, { signal }))
}

export async function fetchBibleChapter(
  translation: string,
  book: number,
  chapter: number,
  signal: AbortSignal,
): Promise<BibleChapter> {
  const queryString = new URLSearchParams({ translation, book: String(book), chapter: String(chapter) })
  return readJson(await fetch(`${mlServiceUrl}/bible-chapter?${queryString}`, { signal }))
}

export async function fetchDevotionals(): Promise<DevotionalInfo[]> {
  return readJson(await fetch(`${mlServiceUrl}/devotionals`))
}

// A search inside the Other books (GET /search-other-books).
export interface BookSearchOptions {
  query: string
  matchMode: 'all' | 'any' | 'phrase'
  // Empty for every book.
  book: string
  sortBy: '' | 'order'
  page: number
  perPage: number
}

export interface BookSearchResult {
  book: string
  book_name: string
  section: number
  section_title: string
  unit: number
  unit_title: string
  heading: string
  // An excerpt, with each word found wrapped in \u0001 and \u0002.
  text: string
}

export interface BookSearchResponse {
  query: string
  total: number
  page: number
  per_page: number
  book_counts: { book: string; name: string; count: number }[]
  results: BookSearchResult[]
}

// A song of the Christian music section (published ones only).
export interface MusicSong {
  id: string
  title: string
  author: string
  // The words as plain text: a line per line, a blank line between verses; '' when there are none.
  lyrics: string
  kind: 'audio' | 'video'
  media_type: string
  // Changes when a file is replaced, so the addresses below ask for the new one.
  version: number
  // The words as a file (a PDF or a picture), shown in place of the typed words; null when there is none.
  words_kind: 'pdf' | 'image' | null
}

export interface MusicSearchResult {
  id: string
  title: string
  author: string
  kind: 'audio' | 'video'
  // An excerpt of the words (or the title), each word found wrapped in \u0001 and \u0002.
  text: string
}

export interface MusicSearchResponse {
  query: string
  total: number
  page: number
  per_page: number
  results: MusicSearchResult[]
}

export async function fetchMusic(): Promise<MusicSong[]> {
  return readJson(await fetch(`${mlServiceUrl}/music`))
}

// Where the player gets a song's file (the server sends it in parts, so the player can skip about).
export function musicFileAddress(song: MusicSong): string {
  return `${mlServiceUrl}/music/${encodeURIComponent(song.id)}/file?v=${song.version}`
}

// A logged-in visitor's playlist: a name and its songs in the order they play (published songs only).
export interface Playlist {
  id: number
  name: string
  song_ids: string[]
  created_at: string
  updated_at: string
}

// Playlists. Each call needs a logged-in visitor (the session cookie says who).
export async function fetchPlaylists(signal?: AbortSignal): Promise<Playlist[]> {
  const response = await fetch(`${mlServiceUrl}/playlists`, { credentials: 'include', signal })
  return (await readJson<{ playlists: Playlist[] }>(response)).playlists
}

// Saves the songs as a playlist; a name the visitor already uses (in any case) replaces that playlist.
export async function savePlaylist(name: string, songIds: string[]): Promise<{ playlist: Playlist; replaced: boolean }> {
  const response = await fetch(`${mlServiceUrl}/playlists`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, song_ids: songIds }),
  })
  return readJson(response)
}

export async function deletePlaylist(id: number): Promise<void> {
  await readJson(await fetch(`${mlServiceUrl}/playlists/${id}`, { method: 'DELETE', credentials: 'include' }))
}

// Where the page gets a song's words file (a PDF or a picture).
export function musicWordsAddress(song: MusicSong): string {
  return `${mlServiceUrl}/music/${encodeURIComponent(song.id)}/words?v=${song.version}`
}

export async function searchMusic(
  options: { query: string; matchMode: 'all' | 'any' | 'phrase'; page: number; perPage: number },
  signal: AbortSignal,
): Promise<MusicSearchResponse> {
  const queryString = new URLSearchParams({
    query: options.query,
    match_mode: options.matchMode,
    page: String(options.page),
    per_page: String(options.perPage),
  })
  return readJson(await fetch(`${mlServiceUrl}/search-music?${queryString}`, { signal }))
}

export async function searchOtherBooks(options: BookSearchOptions, signal: AbortSignal): Promise<BookSearchResponse> {
  const queryString = new URLSearchParams({
    query: options.query,
    match_mode: options.matchMode,
    page: String(options.page),
    per_page: String(options.perPage),
  })
  if (options.book !== '') {
    queryString.set('book', options.book)
  }
  if (options.sortBy !== '') {
    queryString.set('sort_by', options.sortBy)
  }
  return readJson(await fetch(`${mlServiceUrl}/search-other-books?${queryString}`, { signal }))
}

// The search on the welcome page (GET /search-everything): a few hits of each kind, in groups.
export type SiteSearchKind = 'bible' | 'commentary' | 'devotional' | 'book' | 'music'

export type SiteSearchResult =
  | { kind: 'bible'; translation: string; book_number: number; chapter: number; verse: number; reference: string; text: string }
  | {
      kind: 'commentary'
      commentary_id: string
      commentary_name: string
      book_number: number
      chapter: number
      verse: number
      reference: string
      text: string
    }
  | ({ kind: 'devotional' | 'book' } & BookSearchResult)
  // A song of the Christian music: its id, title and author, and an excerpt of its words.
  | { kind: 'music'; id: string; title: string; author: string; text: string }

export interface SiteSearchGroup {
  kind: SiteSearchKind
  total: number
  page: number
  per_page: number
  // The Bible searched, and the words to show in bold in its verses (the other kinds come with excerpts).
  translation?: string
  terms?: string[]
  results: SiteSearchResult[]
}

export async function searchEverything(
  options: { query: string; matchMode: 'all' | 'any' | 'phrase'; kind?: SiteSearchKind; page: number; perPage: number },
  signal: AbortSignal,
): Promise<{ query: string; groups: SiteSearchGroup[] }> {
  const queryString = new URLSearchParams({
    query: options.query,
    match_mode: options.matchMode,
    page: String(options.page),
    per_page: String(options.perPage),
  })
  if (options.kind) {
    queryString.set('kind', options.kind)
  }
  const found: { query: string; groups: SiteSearchGroup[] } = await readJson(
    await fetch(`${mlServiceUrl}/search-everything?${queryString}`, { signal }),
  )
  // Each hit says what kind it is, so it can be drawn and opened without looking at its group.
  return {
    ...found,
    groups: found.groups.map((group) => ({
      ...group,
      results: group.results.map((result) => ({ ...result, kind: group.kind }) as SiteSearchResult),
    })),
  }
}

// The Other books: read a chapter at a time, through the same contents and unit calls as a devotional.
export async function fetchOtherBooks(): Promise<DevotionalInfo[]> {
  return readJson(await fetch(`${mlServiceUrl}/other-books`))
}

export async function fetchDevotionalContents(devotional: string, signal: AbortSignal): Promise<DevotionalContents> {
  const queryString = new URLSearchParams({ devotional })
  return readJson(await fetch(`${mlServiceUrl}/devotional-contents?${queryString}`, { signal }))
}

export async function fetchDevotionalUnit(
  devotional: string,
  section: number,
  unit: number,
  signal: AbortSignal,
): Promise<DevotionalUnit> {
  const queryString = new URLSearchParams({ devotional, section: String(section), unit: String(unit) })
  return readJson(await fetch(`${mlServiceUrl}/devotional-unit?${queryString}`, { signal }))
}

export async function fetchSiteSettings(): Promise<SiteSettings> {
  return readJson(await fetch(`${mlServiceUrl}/site-settings`))
}

// The contact form needs the public reCAPTCHA key (empty when the site has none set up).
export async function fetchContactSettings(): Promise<{ recaptcha_site_key: string }> {
  return readJson(await fetch(`${mlServiceUrl}/contact-settings`))
}

export interface ContactMessage {
  name: string
  email: string
  phone: string
  // The message as Quill writes it: a little HTML, which the server cleans.
  message: string
  recaptcha_token: string
}

export async function sendContactMessage(message: ContactMessage): Promise<void> {
  await readJson(
    await fetch(`${mlServiceUrl}/contact`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(message),
    }),
  )
}

// Accounts. The browser keeps the session in a cookie that scripts cannot read; "include" sends it
// when the page and the service are on different addresses (as they are on a developer's machine).
async function accountRequest(path: string, method: 'GET' | 'POST', body?: object): Promise<AccountUser | null> {
  const response = await fetch(`${mlServiceUrl}/account/${path}`, {
    method,
    credentials: 'include',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  return (await readJson<{ user: AccountUser | null }>(response)).user
}

export function fetchCurrentUser(): Promise<AccountUser | null> {
  return accountRequest('me', 'GET')
}

export function registerAccount(account: NewAccount) {
  return accountRequest('register', 'POST', {
    email: account.email,
    password: account.password,
    password_confirmation: account.passwordConfirmation,
    first_name: account.firstName,
    last_name: account.lastName,
    phone: account.phone,
  })
}

export function logIn(email: string, password: string) {
  return accountRequest('login', 'POST', { email, password })
}

export async function logOut(): Promise<void> {
  await accountRequest('logout', 'POST', {})
}

// Confirming an address, and choosing a new password after forgetting one. Both use a link we emailed.
async function accountAction(path: string, body?: object): Promise<void> {
  await readJson(
    await fetch(`${mlServiceUrl}/account/${path}`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body ?? {}),
    }),
  )
}

export function verifyEmail(token: string) {
  return accountAction('verify', { token })
}

export function resendVerification() {
  return accountAction('resend-verification')
}

export function forgotPassword(email: string) {
  return accountAction('forgot-password', { email })
}

export function resetPassword(token: string, password: string, passwordConfirmation: string) {
  return accountAction('reset-password', { token, password, password_confirmation: passwordConfirmation })
}

// Notes. Both calls need a logged-in visitor (the session cookie says who).
export async function fetchNotes(subject: NoteSubject, signal: AbortSignal): Promise<Note[]> {
  const queryString = new URLSearchParams()
  for (const [name, value] of Object.entries(subject)) {
    queryString.set(name, String(value))
  }
  const response = await fetch(`${mlServiceUrl}/notes?${queryString}`, { credentials: 'include', signal })
  return (await readJson<{ notes: Note[] }>(response)).notes
}

export async function saveNote(subject: NoteSubject, body: string): Promise<Note> {
  const response = await fetch(`${mlServiceUrl}/notes`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...subject, body }),
  })
  return (await readJson<{ note: Note }>(response)).note
}

// One page of the visitor's notes (newest first) for the My notes page, kept to one kind and to the notes
// that have every word of the search.
export async function fetchNotePage(
  options: { query: string; itemType: string; page: number; perPage: number },
  signal: AbortSignal,
): Promise<NotePage> {
  const queryString = new URLSearchParams({ page: String(options.page), per_page: String(options.perPage) })
  if (options.query.trim() !== '') {
    queryString.set('query', options.query.trim())
  }
  if (options.itemType !== 'all') {
    queryString.set('item_type', options.itemType)
  }
  const response = await fetch(`${mlServiceUrl}/notes?${queryString}`, { credentials: 'include', signal })
  return readJson<NotePage>(response)
}

export async function updateNote(id: number, body: string): Promise<Note> {
  const response = await fetch(`${mlServiceUrl}/notes/${id}`, {
    method: 'PUT',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ body }),
  })
  return (await readJson<{ note: Note }>(response)).note
}

export async function deleteNote(id: number): Promise<void> {
  await readJson(await fetch(`${mlServiceUrl}/notes/${id}`, { method: 'DELETE', credentials: 'include' }))
}

// Daily devotional emails. The first three need a logged-in visitor with a confirmed email address.
export async function fetchSubscriptions(signal: AbortSignal): Promise<DevotionalSubscription[]> {
  const response = await fetch(`${mlServiceUrl}/devotional-subscriptions`, { credentials: 'include', signal })
  return (await readJson<{ subscriptions: DevotionalSubscription[] }>(response)).subscriptions
}

export async function saveSubscription(
  devotionalId: string,
  options: { sendTime: string; timezone: string; startSection?: number; startUnit?: number },
): Promise<DevotionalSubscription> {
  const response = await fetch(`${mlServiceUrl}/devotional-subscriptions/${encodeURIComponent(devotionalId)}`, {
    method: 'PUT',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      send_time: options.sendTime,
      timezone: options.timezone,
      start_section: options.startSection ?? null,
      start_unit: options.startUnit ?? null,
    }),
  })
  return (await readJson<{ subscription: DevotionalSubscription }>(response)).subscription
}

export async function deleteSubscription(devotionalId: string): Promise<void> {
  await readJson(
    await fetch(`${mlServiceUrl}/devotional-subscriptions/${encodeURIComponent(devotionalId)}`, {
      method: 'DELETE',
      credentials: 'include',
    }),
  )
}

// The link in every email: stops that devotional's emails with no login. Answers with the devotional's name.
export async function unsubscribeWithToken(token: string): Promise<string> {
  const response = await fetch(`${mlServiceUrl}/subscriptions/unsubscribe?token=${encodeURIComponent(token)}`, {
    method: 'POST',
  })
  return (await readJson<{ devotional: string }>(response)).devotional
}

export interface FaqQuestion {
  id: number
  question: string
}

export interface FaqListing {
  // False when the server has no Gemini key, so no answers can be had.
  available: boolean
  groups: { heading: string; questions: FaqQuestion[] }[]
}

export interface FaqAnswer {
  question_id: number
  question: string
  // Markdown written by Gemini; the page draws it as text, never as HTML.
  answer: string
  // The Scripture references found in it (each once), with the verse each begins at.
  references: FaqReference[]
  // The site owner's note on the question, as HTML cleaned by the server; '' when it has none.
  owner_note: string
}

export interface FaqReference {
  text: string
  book: number
  chapter: number
  verse: number
}

// The answer to a visitor's own question (only for an account an administrator allowed).
export interface OpenQuestionAnswer {
  // The question as plain text, as it was sent.
  question: string
  answer: string
  references: FaqReference[]
}

export async function askOpenQuestion(questionHtml: string): Promise<OpenQuestionAnswer> {
  const response = await fetch(`${mlServiceUrl}/faq/ask`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question: questionHtml }),
  })
  // The server's own refusals (the daily limit, a question too long) carry a message; the web server's
  // rate limit does not.
  if (!response.ok) {
    let message =
      response.status === 429
        ? "You're asking too quickly. Please wait a minute and try again."
        : 'The answer could not be written just now. Please try again in a minute.'
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') {
        message = body.detail
      }
    } catch {
      // No JSON body; keep the message above.
    }
    throw new Error(message)
  }
  return response.json()
}

export async function fetchFaqQuestions(): Promise<FaqListing> {
  return readJson(await fetch(`${mlServiceUrl}/faq`))
}

export async function fetchFaqAnswer(questionId: number): Promise<FaqAnswer> {
  const response = await fetch(`${mlServiceUrl}/faq/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question_id: questionId }),
  })
  if (response.status === 429) {
    throw new Error("You're asking too quickly. Please wait a minute and try again.")
  }
  if (response.status >= 500) {
    throw new Error('The FAQ answers are not available right now. Please try again later.')
  }
  return readJson(response)
}
