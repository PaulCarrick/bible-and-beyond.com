import type { Destination } from './types'

// An address that opens the Bible reader at a verse, such as /?read=BSB&book=62&chapter=4&verse=1. The FAQ's
// verse links use it so they can open in a new tab. Both halves are here so the format stays the same.

export function verseAddress(translation: string, book: number, chapter: number, verse: number): string {
  const parameters = new URLSearchParams({
    read: translation,
    book: String(book),
    chapter: String(chapter),
    verse: String(verse),
  })
  return `/?${parameters}`
}

// The verse the page's address asks for, or null. Numbers that cannot be a verse are ignored.
export function readVerseAddress(search: string): Destination | null {
  const parameters = new URLSearchParams(search)
  const translation = parameters.get('read')
  const book = Number(parameters.get('book'))
  const chapter = Number(parameters.get('chapter'))
  const verse = Number(parameters.get('verse') ?? 1)
  const isWhole = (value: number, highest: number) => Number.isInteger(value) && value >= 1 && value <= highest
  if (!translation || !isWhole(book, 66) || !isWhole(chapter, 150) || !isWhole(verse, 176)) {
    return null
  }
  return { id: Date.now(), kind: 'bible', translation, book, chapter, verse }
}
