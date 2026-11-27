export type MatchMode = 'all' | 'any' | 'phrase'
// The Bible search also offers 'ai': Google's Gemini suggests the verses (accounts with open_ai_queries only).
// 'ai': search by meaning (accounts with open_ai_queries); 'archive': the Internet Archive (anyone).
export type SearchMatchMode = MatchMode | 'ai' | 'archive'
export type SortField = 'verse' | 'text'
export type SortDirection = 'asc' | 'desc'
export type PerPage = number | 'automatic'

export type TranslationSource = 'local' | 'api_bible'
// What a search looked through: Bibles stored here, a licensed Bible, or the commentaries.
export type SearchSource = TranslationSource | 'commentary'

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
  matchMode: SearchMatchMode
  wholeWords: boolean
  translations: string[]
  // Only for a commentary search: which commentary (null for all of them).
  commentary: string | null
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
  // Only for a commentary search: the note's commentary. text is then an excerpt with the words
  // found wrapped in the control characters \u0001 and \u0002.
  commentary_id?: string
  commentary_name?: string
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
  // Only for a Bible that has them (the BSB): [start, end, "H7225"] over text, one for each English
  // word that stands for a Hebrew or Greek word.
  links?: [number, number, string][]
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

export type ContextKind = 'context' | 'chapter' | 'parallel' | 'related' | 'words' | 'lexicon' | 'commentary' | 'note'

// A verse that a window is about, named well enough to ask for more about it.
export interface VerseTarget {
  translation: string
  book_number: number
  chapter: number
  verse: number
  reference: string
  // Only for a lexicon entry: the Strong's number whose entry the window shows.
  strong_code?: string
  // Only for a notes window about a commentary note or a devotional reading (a verse is the default).
  subject?: NoteSubject
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
  source: SearchSource
  fums_token?: string | null
  copyright?: string
  query: string
  terms: string[]
  total: number
  page: number
  per_page: number
  book_counts: BookCount[]
  results: SearchResult[]
  // Only when the query was a Strong's number such as G0025: the word it stands for.
  strong?: StrongWord
  // Only for an AI search: the verses are the ones Gemini suggested, and how many it named.
  ai?: boolean
  ai_verse_count?: number
}

export interface StrongWord {
  code: string
  language: 'hebrew' | 'greek'
  original: string
  transliteration: string
  gloss: string
}

// Original Words: the Hebrew or Greek words of one verse, each with its meaning in the lexicon.
export interface OriginalWord {
  original: string
  transliteration: string
  english: string
  strong_code: string | null
  grammar: string
  gloss: string | null
}

export interface OriginalWordsResponse {
  book_number: number
  book_name: string
  chapter: number
  verse: number
  language: 'hebrew' | 'greek'
  words: OriginalWord[]
}

// One lexicon entry (a Strong's number) with the first verses that use the word.
export interface LexiconVerse {
  book_number: number
  reference: string
  chapter: number
  verse: number
  text: string | null
}

export interface LexiconEntry {
  strong_code: string
  language: 'hebrew' | 'greek'
  original: string
  transliteration: string
  morphology: string
  gloss: string
  definition: string
  verse_total: number
  shown: number
  verses: LexiconVerse[]
}

// Commentaries: the public-domain commentaries that have notes on a verse, and the text of one.
export interface CommentaryChoice extends CommentaryOrigin {
  id: string
  name: string
  short_name: string
  characters: number
  // The verses the note covers, such as "John 3:1–21".
  covers: string
  // The verse the note begins at.
  start_verse: number
}

export interface CommentaryResponse {
  book_number: number
  book_name: string
  chapter: number
  verse: number
  commentaries: CommentaryChoice[]
  selected: string
  covers: string
  // The verse the shown note begins at (the verse a visitor's notes on it are kept under).
  note_verse: number
  text: string
  chapter_introduction: string | null
  book_introduction: string | null
  // Scripture references inside each text: [start, end, "book:chapter:verse"] over that text.
  references: [number, number, string][]
  chapter_introduction_references: [number, number, string][]
  book_introduction_references: [number, number, string][]
  // The same with its formatting, from a PDF or Word upload (references as links); absent for plain text.
  html?: string
  chapter_introduction_html?: string
  book_introduction_html?: string
  // The PDF pages each came from ("Preserve original pages" on the Upload form), shown in place of the text.
  original_pages?: OriginalPages
  chapter_introduction_pages?: OriginalPages
  book_introduction_pages?: OriginalPages
}

// A PDF's pages kept as pictures (document is the folder key), from first to last page, from 1.
export interface OriginalPages {
  document: string
  first: number
  last: number
}

// One commentary, as listed for choosing which to search.
// Where a commentary's text came from and its licence, for the credit (an uploaded one may differ).
export interface CommentaryOrigin {
  source_name: string
  source_url: string
  license_url: string
}

export interface CommentarySource extends CommentaryOrigin {
  id: string
  name: string
  short_name: string
}

// Browsing a commentary: what it has notes on, and one chapter of it.
export interface CommentaryContents {
  commentary: CommentarySource
  books: { number: number; name: string; chapters: number[] }[]
}

export interface ChapterNeighbour {
  book_number: number
  book_name: string
  chapter: number
}

export interface CommentaryNote {
  verse: number
  end_verse: number | null
  // The verses the note covers, such as "John 3:1–21".
  covers: string
  text: string
  references: [number, number, string][]
  // The same with its formatting, from a PDF or Word upload (references as links); absent for plain text.
  html?: string
  original_pages?: OriginalPages
}

export interface CommentaryChapter {
  commentary: CommentarySource
  book_number: number
  book_name: string
  chapter: number
  chapter_introduction: string | null
  chapter_introduction_references: [number, number, string][]
  book_introduction: string | null
  book_introduction_references: [number, number, string][]
  // The same with its formatting, from a PDF or Word upload (references as links); absent for plain text.
  chapter_introduction_html?: string
  book_introduction_html?: string
  chapter_introduction_pages?: OriginalPages
  book_introduction_pages?: OriginalPages
  entries: CommentaryNote[]
  previous: ChapterNeighbour | null
  next: ChapterNeighbour | null
}

// Reading a Bible a chapter at a time: what a Bible has, and one chapter of it.
export interface BibleContents {
  translation: { code: string; name: string; language: string }
  books: { number: number; name: string; chapters: number[] }[]
}

export interface BibleVerse {
  verse: number
  text: string
  // Only for a Bible that has them (the BSB): [start, end, "H7225"] over text.
  links?: [number, number, string][]
}

export interface BibleChapter {
  translation: { code: string; name: string; language: string }
  book_number: number
  book_name: string
  chapter: number
  verses: BibleVerse[]
  previous: ChapterNeighbour | null
  next: ChapterNeighbour | null
}

// Devotionals: books of daily readings or chapters, in the public domain.
export interface DevotionalInfo {
  id: string
  name: string
  author: string
  // "daily": the sections are months and the units are days (a morning and an evening reading).
  // "chapters": the sections are books or parts and the units are chapters.
  kind: 'daily' | 'chapters'
  source_name: string
  source_url: string
  translator: string | null
  // Its own credit line, shown instead of "... is in the public domain"; null for the old public-domain texts.
  credit: string | null
}

export interface DevotionalContents {
  devotional: DevotionalInfo
  sections: { number: number; title: string; units: { number: number; title: string }[] }[]
}

export interface DevotionalNeighbour {
  section: number
  unit: number
  title: string
  section_title: string
}

export interface DevotionalEntry {
  // "Morning" or "Evening" for a daily reading; empty for a chapter.
  heading: string
  text: string
  // A linked statement (the Apostles' Creed's) adds the verse as written, "Luke 1:35", for its tooltip.
  references: [number, number, string, string?][]
  // The same with its formatting, from a PDF or Word upload (references as links); absent for plain text.
  html?: string
  original_pages?: OriginalPages
}

// One day or chapter, as the server sends it.
export interface DevotionalUnit {
  devotional: DevotionalInfo
  section: number
  section_title: string
  unit: number
  title: string
  entries: DevotionalEntry[]
  previous: DevotionalNeighbour | null
  next: DevotionalNeighbour | null
}

// The two texts an administrator sets in Drupal: the name of the site and its copyright line.
export interface SiteSettings {
  title: string
  copyright: string
  // The icons an administrator uploaded on the Site settings screen, as addresses on the ML service
  // ("/site-icon/header?v=..."); null (or missing) means the site's own icon.
  header_icon?: string | null
  tab_icon?: string | null
  // The welcome page's opening words, set in the editor of the Site settings screen: HTML the server cleaned
  // (links and formatting only). Missing: the site's own words.
  welcome_html?: string
  // When true only the sign-in pages work until a visitor logs in (the API refuses the rest).
  login_required?: boolean
}

// A visitor who has set up an account and is logged in.
export interface AccountUser {
  id: number
  // null for an account set up with a phone number only (2026-11-17): it logs in with it and is never emailed.
  email: string | null
  // True once the owner followed the link emailed to the address.
  email_verified: boolean
  // The account logs in with its phone number, and whether the code texted to it was typed in.
  logs_in_with_phone: boolean
  phone_verified: boolean
  // An administrator allowed this account to ask the AI its own questions (the FAQ page); off unless set in Drupal.
  open_ai_queries: boolean
  // Given when the account was set up; '' for accounts set up before the names were asked for.
  first_name: string
  last_name: string
  // Optional; '' when none was given.
  phone: string
  // An administrator allowed this account to read and write Conversations; off unless set in Drupal.
  use_conversations: boolean
  // Text messages (sms.py): the phone is a cell number; the member asked for texts; they replied STOP since.
  phone_is_cell: boolean
  sms_opt_in: boolean
  sms_stopped: boolean
  // How the member's notices reach them (Send via Email, Send via SMS on My account): one or both.
  send_via_email: boolean
  send_via_sms: boolean
  // Send Multimedia Messages: the verse a day and the devotionals as a picture.
  send_multimedia: boolean
  // An administrator allowed this account its own notes, pins and routes on the maps; off unless set in Drupal.
  use_maps: boolean
  // An administrator allowed this account to share its lists on Public lists; off unless set in Drupal.
  share_lists: boolean
  // A member of at least one group (Drupal Groups): only then does the menu offer My scheduled tasks.
  in_a_group?: boolean
  // The member's own picture (My account; 2026-11-23): its address on the service (headShotAddress), or null.
  head_shot: string | null
}

// What the Set up account form sends.
export interface NewAccount {
  email: string
  password: string
  passwordConfirmation: string
  firstName: string
  lastName: string
  phone: string
  phoneIsCell: boolean
  // How messages reach the member: one or both (SMS needs a cell number; ticking it is the consent to texts).
  sendViaEmail: boolean
  sendViaSms: boolean
  sendMultimedia: boolean
  // A verse a day: its time of day and the visitor's time zone.
  verseADay: boolean
  verseTime: string
  timezone: string
}

// The verse a day of the logged-in member (verse_a_day.py).
export interface VerseSubscription {
  send_time: string
  timezone: string
  last_sent_on: string | null
}

// A note a logged-in visitor wrote about a verse, a commentary note or a devotional reading.
export interface Note {
  id: number
  // 'map': one entry of the My notes list for a map the visitor marked, listing their notes, pins and routes on it
  // (source_code is the map's id); it is changed on the map, not here.
  item_type: 'bible_verse' | 'commentary' | 'devotional' | 'map'
  source_code: string
  book_number: number | null
  chapter: number | null
  verse: number | null
  section: number | null
  unit: number | null
  // What the note is about, such as "John 3:16" or "Genesis 1:1–2 (Matthew Henry)".
  title: string
  // A little HTML, cleaned by the server.
  body: string
  created_at: string
  updated_at: string
  // A map's entry: how many notes, pins and routes it lists.
  mark_count?: number
}

// What a note is about: a Bible verse, a commentary note (its commentary and the verse it begins at) or a
// devotional reading (its devotional, section and unit). Only the fields that belong to the type are set.
export interface NoteSubject {
  item_type: 'bible_verse' | 'commentary' | 'devotional'
  // The translation read, the commentary or the devotional, by id.
  source_code: string
  book_number?: number
  chapter?: number
  verse?: number
  section?: number
  unit?: number
}

// One page of a visitor's notes, with how many match in all.
export interface NotePage {
  notes: Note[]
  total: number
  page: number
  per_page: number
}

// Where a post is: Conversations, or the Prayer Wall ('prayer'). A post shows only on its own board.
export type ConversationBoard = 'conversations' | 'prayer'

// A post in Conversations or on the Prayer Wall (members' posts; anyone may read them).
export interface ConversationPost {
  id: number
  title: string
  // A little HTML from the editor, cleaned by the server.
  body: string
  created_at: string
  updated_at: string
  // The author's name, or "A member" when the account has none (never the address).
  author: string
  // Whether the member reading it wrote it (only then can it be changed or deleted).
  is_mine: boolean
  board: ConversationBoard
  // The Prayer Wall choices (always false on Conversations): the author's name is not shown ("Anonymous"); only
  // the author (and the site administrators) see it; it is emailed to the prayer list.
  is_anonymous: boolean
  is_private: boolean
  email_to_prayer_list: boolean
  // When its author marked the request answered (Prayer Wall only), or null. Answered requests are not emailed.
  answered_at: string | null
  // Conversations only, and true only for its author: new replies by others are emailed to the author.
  email_replies: boolean
  // Prayer Wall, for its author only: emailed to a group ("group") or its leader ("leader"), the group and its
  // name, and when the email went (null while it is on its way).
  share_with?: 'group' | 'leader' | null
  share_group_id?: number | null
  share_group_name?: string | null
  shared_at?: string | null
  // A post to one member (2026-11-23): who it went to (is_me when that is the reader), or null for everyone.
  recipient?: { id: number; name: string; is_me: boolean } | null
  // For its author only: whether the member has accepted posts from them yet.
  delivery?: 'pending' | 'accepted' | 'declined' | null
  // Members' replies to it, oldest first.
  replies: ConversationReply[]
}

// Someone who has asked to send the reader posts to them alone, and the reader's answer.
export interface MessagePermission {
  sender_id: number
  sender: string
  status: 'pending' | 'accepted' | 'declined'
  requested_at: string
  answered_at: string | null
}

// A reply to a Conversations post: any allowed member may reply; only its author can change or delete it.
export interface ConversationReply {
  id: number
  post_id: number
  body: string
  created_at: string
  updated_at: string
  author: string
  is_mine: boolean
}

export interface ConversationPage {
  posts: ConversationPost[]
  total: number
  page: number
  per_page: number
  // Whether the visitor may write posts and replies (logged in with use_conversations). Anyone may read.
  can_post: boolean
}

// A place a reader is asked to open at: set when a note's link is followed, with a new id each time so
// following the same link twice goes there twice.
export type Destination =
  // strongCode (G0264, H7225): also open that word's lexicon entry over the verse.
  | { id: number; kind: 'bible'; translation: string; book: number; chapter: number; verse: number; strongCode?: string }
  | { id: number; kind: 'commentary'; commentary: string; book: number; chapter: number; verse: number }
  // onlyIfFound (an address such as /books?book=apostles-creed): when there is no such devotional or book, stay
  // on the list rather than open the first one. A section and unit it does not have open its start.
  | { id: number; kind: 'devotional'; devotional: string; section: number; unit: number; onlyIfFound?: boolean }

// A devotional the logged-in visitor gets by email each day.
// The weekly prayer list email of the logged-in visitor (prayer_list.py).
export interface PrayerListSubscription {
  // 0 Monday to 6 Sunday.
  send_weekday: number
  send_time: string
  timezone: string
  last_sent_on: string | null
}

// The choices of a post being saved: the three Prayer Wall ones, and "email me replies" on Conversations.
export interface PostOptions {
  isAnonymous: boolean
  isPrivate: boolean
  emailToPrayerList: boolean
  emailReplies: boolean
  // Prayer Wall: email it to a group the member is in, or to its leader (sent at once; the post is private).
  shareWith?: 'group' | 'leader' | null
  shareGroupId?: number | null
  // Conversations, a new post only: send it to this member alone (2026-11-23).
  recipientId?: number | null
}

export interface DevotionalSubscription {
  devotional_id: string
  devotional_name: string
  kind: 'daily' | 'chapters'
  // The time of day, such as "07:00", in the visitor's own time zone.
  send_time: string
  timezone: string
  // For a devotional with chapters: the one that will be sent next.
  next_section: number | null
  next_unit: number | null
  next_title: string | null
  last_sent_on: string | null
}
