import { useMemo } from 'react'
import type { MouseEvent } from 'react'
import { formattedHtmlForPage } from './api'
import { highlightHtml } from './highlightHtml'
import { verseAddress } from './verseAddress'

interface FormattedTextProps {
  // Cleaned HTML from the server (a PDF or Word upload), with each Scripture reference a
  // <button class="reference-link" data-verse="book:chapter:verse">.
  html: string
  // Words searched for, highlighted.
  terms: string[]
  // The Bible a reference opens in when it goes to a new tab (Shift, Ctrl or Cmd held, or the middle button).
  translation: string
  onOpenReference: (book: number, chapter: number, verse: number, shownText: string, element: HTMLElement) => void
}

function referenceIn(event: MouseEvent<HTMLDivElement>) {
  const target = event.target as HTMLElement
  return target.closest<HTMLButtonElement>('button.reference-link[data-verse]')
}

// A text that keeps its formatting (headings, bold, italic, lists, quotations, tables, pictures, footnotes). The
// server cleaned it when it was saved; here the search words are wrapped in <mark> in its text only, the
// pictures are fetched from the service, and a click on a reference opens it like the references of plain texts.
function FormattedText({ html, terms, translation, onOpenReference }: FormattedTextProps) {
  const termsKey = terms.join('\u0000')
  const shown = useMemo(
    () => formattedHtmlForPage(highlightHtml(html, termsKey === '' ? [] : termsKey.split('\u0000'))),
    [html, termsKey],
  )

  function open(event: MouseEvent<HTMLDivElement>, newTab: boolean) {
    const reference = referenceIn(event)
    if (!reference) {
      return
    }
    const [book, chapter, verse] = (reference.dataset.verse ?? '').split(':').map(Number)
    if (!book || !chapter || !verse) {
      return
    }
    event.preventDefault()
    if (newTab) {
      window.open(verseAddress(translation, book, chapter, verse), '_blank', 'noopener')
    } else {
      onOpenReference(book, chapter, verse, reference.textContent ?? '', reference)
    }
  }

  return (
    <div
      className="formatted-text"
      dangerouslySetInnerHTML={{ __html: shown }}
      onClick={(event) => open(event, event.shiftKey || event.ctrlKey || event.metaKey)}
      onAuxClick={(event) => {
        if (event.button === 1) {
          open(event, true)
        }
      }}
      onMouseDown={(event) => {
        // Shift-click on a reference would select text, and the middle button would start scrolling.
        if (referenceIn(event) && (event.shiftKey || event.button === 1)) {
          event.preventDefault()
        }
      }}
    />
  )
}

export default FormattedText
