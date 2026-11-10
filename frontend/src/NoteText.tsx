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
}

// The text of a commentary note as paragraphs, with its scripture references as links.
function NoteText({ text, references, terms, translation = 'BSB', onOpenReference }: NoteTextProps) {
  const verseLabels = new Map(references.filter((reference) => reference[3]).map((reference) => [reference[2], reference[3]]))
  const linkOptions: LinkOptions = {
    ...referenceLinkOptions,
    titleFor: (code, shownText) => `Show ${verseLabels.get(code) ?? shownText.trim()} in context`,
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
