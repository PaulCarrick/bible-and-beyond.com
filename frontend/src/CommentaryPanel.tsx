import CommentaryCredit from './CommentaryCredit'
import NoteText from './NoteText'
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
  function openReference(book: number, chapter: number, verse: number, shownText: string) {
    onOpenVerse('context', { translation, book_number: book, chapter, verse, reference: shownText })
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
          <p>
            <button
              type="button"
              className="link-button"
              onClick={() =>
                onOpenVerse('note', {
                  translation,
                  book_number: commentary.book_number,
                  chapter: commentary.chapter,
                  verse: commentary.note_verse,
                  reference: `${commentary.covers} (${chosen?.short_name ?? ''})`,
                  subject: {
                    item_type: 'commentary',
                    source_code: commentary.selected,
                    book_number: commentary.book_number,
                    chapter: commentary.chapter,
                    verse: commentary.note_verse,
                  },
                })
              }
            >
              Notes
              <span className="visually-hidden"> on this commentary note</span>
            </button>
          </p>
          <div className="commentary-text">
            <NoteText text={commentary.text} references={commentary.references} terms={terms} translation={translation} onOpenReference={openReference} />
          </div>
          {commentary.chapter_introduction && (
            <details className="commentary-introduction">
              <summary>
                Introduction to {commentary.book_name} {commentary.chapter}
              </summary>
              <NoteText
                text={commentary.chapter_introduction}
                translation={translation}
                references={commentary.chapter_introduction_references}
                terms={[]}
                onOpenReference={openReference}
              />
            </details>
          )}
          {commentary.book_introduction && (
            <details className="commentary-introduction">
              <summary>Introduction to {commentary.book_name}</summary>
              <NoteText
                text={commentary.book_introduction}
                translation={translation}
                references={commentary.book_introduction_references}
                terms={[]}
                onOpenReference={openReference}
              />
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
