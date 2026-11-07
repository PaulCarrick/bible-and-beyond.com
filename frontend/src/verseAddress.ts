import type { MouseEvent } from 'react'
import type { Destination } from './types'

// An address that opens the Bible reader at a verse, such as /?read=BSB&book=62&chapter=4&verse=1. The FAQ's
// verse links use it so they can open in a new tab, and so do the site's other verse buttons when Shift, Ctrl or
// Cmd is held or the middle button is used. Both halves are here so the format stays the same.

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

export interface VerseInBible {
  translation: string
  book: number
  chapter: number
  verse: number
}

// Whether a click asks for a new tab: Shift, Ctrl or Cmd held, or the middle button.
export function wantsNewTab(event: MouseEvent<HTMLElement>): boolean {
  return event.button === 1 || event.shiftKey || event.ctrlKey || event.metaKey
}

export function openVerseInNewTab({ translation, book, chapter, verse }: VerseInBible) {
  window.open(verseAddress(translation || 'BSB', book, chapter, verse), '_blank', 'noopener')
}

// The click handlers of a button that opens a verse on this page (Show in Context, Full Chapter, a reference in a
// note). A plain click calls openHere as before; a click with Shift, Ctrl or Cmd, or with the middle button,
// opens the Bible reader at the verse in a new tab instead.
export function verseButtonProps(verse: VerseInBible, openHere: (element: HTMLElement) => void) {
  return {
    onClick: (event: MouseEvent<HTMLElement>) => {
      if (wantsNewTab(event)) {
        event.preventDefault()
        openVerseInNewTab(verse)
      } else {
        openHere(event.currentTarget)
      }
    },
    onAuxClick: (event: MouseEvent<HTMLElement>) => {
      if (event.button === 1) {
        event.preventDefault()
        openVerseInNewTab(verse)
      }
    },
    // Shift-click would otherwise select text, and a middle press would start the browser's autoscroll.
    onMouseDown: (event: MouseEvent<HTMLElement>) => {
      if (event.button === 1 || event.shiftKey) {
        event.preventDefault()
      }
    },
  }
}
