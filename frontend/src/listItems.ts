import type { BookSearchResult, MapSearchResult, MusicSearchResult, SiteSearchResult } from './api'
import type { SearchResult } from './types'

// My lists (saved_lists.py): an entry is kept as its search showed it, so a list never searches again. Every search
// turns its results into these with the builders below.
export type ListItemKind = 'bible' | 'commentary' | 'devotional' | 'book' | 'music' | 'map' | 'faq'

export interface ListItemTarget {
  translation?: string
  book?: number
  chapter?: number
  verse?: number
  commentary?: string
  devotional?: string
  section?: number
  unit?: number
  song?: string
  map?: string
  question?: string
}

export interface ListItem {
  kind: ListItemKind
  // One per item: the same verse in another Bible, or another commentary's note, is another entry.
  key: string
  // What the search showed: a place or title ("John 3:16"), a source ("BSB", a commentary, a book) and the text.
  title: string
  source: string
  text: string
  // Where to open it.
  target: ListItemTarget
}

// The search's highlight markers (\u0001 and \u0002) are left out of what is kept.
const plain = (text: string) => text.replaceAll('\u0001', '').replaceAll('\u0002', '').trim()

export function bibleItem(result: SearchResult): ListItem {
  return {
    kind: 'bible',
    key: `bible:${result.translation}:${result.book_number}:${result.chapter}:${result.verse}`,
    title: result.reference,
    source: result.translation,
    text: plain(result.text),
    target: { translation: result.translation, book: result.book_number, chapter: result.chapter, verse: result.verse },
  }
}

export function commentaryItem(result: SearchResult): ListItem {
  return {
    kind: 'commentary',
    key: `commentary:${result.commentary_id}:${result.book_number}:${result.chapter}:${result.verse}`,
    title: result.reference,
    source: result.commentary_name ?? '',
    text: plain(result.text),
    target: { commentary: result.commentary_id, book: result.book_number, chapter: result.chapter, verse: result.verse },
  }
}

export function bookItem(result: BookSearchResult, kind: 'devotional' | 'book'): ListItem {
  const place = [result.section_title !== result.book_name ? result.section_title : '', result.unit_title, result.heading]
    .filter((part) => part !== '')
    .join(' · ')
  return {
    kind,
    key: `${kind}:${result.book}:${result.section}:${result.unit}`,
    title: place || result.book_name,
    source: result.book_name,
    text: plain(result.text),
    target: { devotional: result.book, section: result.section, unit: result.unit },
  }
}

export function songItem(result: MusicSearchResult): ListItem {
  return { kind: 'music', key: `music:${result.id}`, title: result.title, source: result.author, text: plain(result.text), target: { song: result.id } }
}

export function mapItem(result: MapSearchResult | { id: string; title: string; verses_text: string; text: string }): ListItem {
  return { kind: 'map', key: `map:${result.id}`, title: result.title, source: result.verses_text, text: plain(result.text), target: { map: result.id } }
}

// An entry of Search everything, whatever its kind.
export function siteItem(result: SiteSearchResult, groupKind: string): ListItem {
  switch (result.kind) {
    case 'bible':
      return bibleItem({ ...result, book_name: '' })
    case 'commentary':
      return commentaryItem({ ...result, translation: '', book_name: '' })
    case 'music':
      return songItem({ ...result, kind: 'audio' })
    case 'map':
      return mapItem(result)
    case 'faq':
      return { kind: 'faq', key: `faq:${result.question}`, title: result.question, source: result.group, text: plain(result.text), target: { question: result.question } }
    default:
      return bookItem(result, groupKind === 'book' ? 'book' : 'devotional')
  }
}
