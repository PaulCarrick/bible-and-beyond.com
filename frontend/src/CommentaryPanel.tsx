import CommentaryCredit from './CommentaryCredit'
import { highlightLinked } from './highlight'
import type { LinkOptions } from './highlight'
import type { CommentaryResponse, ContextKind, VerseTarget } from './types'

interface CommentaryPanelProps {
  commentary: CommentaryResponse
  // The commentary asked for. It differs from commentary.selected while another one is loading.
  requestedId: string
  onChangeCommentary: (commentaryId: string) => void
  // Words searched for in the commentaries, shown in bold in the note (none otherwise).
  terms: string[]
  // The Bible a reference opens in.
  translation: string
  onOpenVerse: (kind: ContextKind, target: VerseTarget) => void
}

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

function CommentaryPanel({
  commentary,
  requestedId,
  onChangeCommentary,
  terms,
  translation,
  onOpenVerse,
}: CommentaryPanelProps) {
  const isLoading = commentary.selected !== requestedId
  const chosen = commentary.commentaries.find((entry) => entry.id === commentary.selected)

  // A reference opens its verse in context, on top of this window, so Back returns to the note.
  function openReference(code: string, shownText: string) {
    const [book, chapter, verse] = code.split(':').map(Number)
    onOpenVerse('context', {
      translation,
      book_number: book,
      chapter,
      verse,
      reference: shownText.trim(),
    })
  }

  // The paragraphs of a text with its references (and, for the note, the search words) marked.
  function renderParagraphs(text: string, references: [number, number, string][], words: string[]) {
    return paragraphsOf(text).map((paragraph) => {
      const links = references
        .filter(([start, end]) => start >= paragraph.start && end <= paragraph.start + paragraph.text.length)
        .map(([start, end, code]): [number, number, string] => [start - paragraph.start, end - paragraph.start, code])
      return (
        <p key={paragraph.start}>
          {highlightLinked(paragraph.text, words, false, links, (code) => {
            const link = links.find(([, , linkCode]) => linkCode === code)
            openReference(code, link ? paragraph.text.slice(link[0], link[1]) : '')
          }, referenceLinkOptions)}
        </p>
      )
    })
  }

  return (
    <>
      <div className="related-tabs" role="group" aria-label="Which commentary to show">
        {commentary.commentaries.map((entry) => (
          <button
            type="button"
            key={entry.id}
            className="related-tab"
            title={entry.name}
            aria-pressed={requestedId === entry.id}
            onClick={() => onChangeCommentary(entry.id)}
          >
            {entry.short_name}
          </button>
        ))}
      </div>

      {isLoading ? (
        <p>Loading…</p>
      ) : (
        <>
          <p className="commentary-covers">
            {chosen?.name}: notes on {commentary.covers}
          </p>
          <div className="commentary-text">{renderParagraphs(commentary.text, commentary.references, terms)}</div>
          {commentary.chapter_introduction && (
            <details className="commentary-introduction">
              <summary>
                Introduction to {commentary.book_name} {commentary.chapter}
              </summary>
              {renderParagraphs(commentary.chapter_introduction, commentary.chapter_introduction_references, [])}
            </details>
          )}
          {commentary.book_introduction && (
            <details className="commentary-introduction">
              <summary>Introduction to {commentary.book_name}</summary>
              {renderParagraphs(commentary.book_introduction, commentary.book_introduction_references, [])}
            </details>
          )}
          <p className="related-note">
            <CommentaryCredit />
          </p>
        </>
      )}
    </>
  )
}

export default CommentaryPanel
