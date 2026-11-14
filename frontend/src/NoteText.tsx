import { useState } from 'react'
import FormattedText from './FormattedText'
import OriginalPages from './OriginalPages'
import type { OriginalPages as OriginalPagesType } from './types'
import { highlightLinked } from './highlight'
import type { LinkOptions } from './highlight'

// Every line of the old texts is a paragraph or a point of an outline (none are wrapped by hand).
// start is where the paragraph begins in the whole text, to find the references inside it.
function paragraphsOf(text: string) {
  const paragraphs: { text: string; start: number }[] = []
  let position = 0
  for (const piece of text.split(/(\n+)/)) {
    if (piece.trim() !== '') {
      paragraphs.push({ text: piece, start: position })
    }
    position += piece.length
  }
  return paragraphs
}

const referenceLinkOptions: LinkOptions = {
  className: 'reference-link',
  isTabbable: true,
  titleFor: (_code, shownText) => `Show ${shownText.trim()} in context`,
}

interface NoteTextProps {
  text: string
  // Scripture references in the text: [start, end, "book:chapter:verse"] over the whole text, and for a linked
  // statement (words that are not a reference) the verse as written, "Luke 1:35", for the tooltip.
  references: [number, number, string, string?][]
  // Words searched for, shown in bold.
  terms: string[]
  // The Bible a reference opens in when it goes to a new tab (Shift, Ctrl or Cmd held); the BSB when not given.
  translation?: string
  // A reference was chosen: its verse, the words as written, and the link that was used.
  onOpenReference: (book: number, chapter: number, verse: number, shownText: string, element: HTMLElement) => void
  // The text with its formatting (a PDF or Word upload); when given, it is shown instead of the plain text.
  html?: string
  // The PDF pages it came from ("Preserve original pages"): shown as pictures, with a button for the text.
  originalPages?: OriginalPagesType
}

// A reading kept with its original pages: the pages, or its text, with a button to switch. Opened from a search
// (words to show in bold), it starts on the text, where the words are.
function WithOriginalPages(props: NoteTextProps & { originalPages: OriginalPagesType }) {
  const [showsText, setShowsText] = useState(props.terms.length > 0)
  return (
    <>
      <p className="original-pages-switch">
        <button type="button" className="secondary-button small-button" onClick={() => setShowsText(!showsText)}>
          {showsText ? 'Show the original pages' : 'Show the text'}
        </button>
        <span>
          {showsText
            ? 'The text read from the original pages; it may have small mistakes.'
            : `The original page${props.originalPages.first === props.originalPages.last ? '' : 's'}.`}
        </span>
      </p>
      {showsText ? <NoteText {...props} originalPages={undefined} /> : <OriginalPages pages={props.originalPages} />}
    </>
  )
}

// The text of a commentary note as paragraphs, with its scripture references as links.
function NoteText(props: NoteTextProps) {
  const { text, references, terms, translation = 'BSB', onOpenReference, html, originalPages } = props
  if (originalPages) {
    return <WithOriginalPages {...props} originalPages={originalPages} />
  }
  if (html) {
    return <FormattedText html={html} terms={terms} translation={translation} onOpenReference={onOpenReference} />
  }
  const verseLabels = new Map(references.filter((reference) => reference[3]).map((reference) => [reference[2], reference[3]]))
  const linkOptions: LinkOptions = {
    ...referenceLinkOptions,
    titleFor: (code, shownText) => `Show ${verseLabels.get(code) ?? shownText.trim()} in context`,
    isPlainText: (code) => verseLabels.has(code),
    newTabVerse: (code) => {
      const [book, chapter, verse] = code.split(':').map(Number)
      return { translation, book, chapter, verse }
    },
  }
  return (
    <>
      {paragraphsOf(text).map((paragraph) => {
        const links = references
          .filter(([start, end]) => start >= paragraph.start && end <= paragraph.start + paragraph.text.length)
          .map(([start, end, code]): [number, number, string] => [start - paragraph.start, end - paragraph.start, code])
        return (
          <p key={paragraph.start}>
            {highlightLinked(
              paragraph.text,
              terms,
              false,
              links,
              (code, element) => {
                const [book, chapter, verse] = code.split(':').map(Number)
                const link = links.find(([, , linkCode]) => linkCode === code)
                onOpenReference(book, chapter, verse, link ? paragraph.text.slice(link[0], link[1]) : '', element)
              },
              linkOptions,
            )}
          </p>
        )
      })}
    </>
  )
}

export default NoteText
