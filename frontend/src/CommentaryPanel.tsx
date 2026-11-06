import CommentaryCredit from './CommentaryCredit'
import type { CommentaryResponse } from './types'

interface CommentaryPanelProps {
  commentary: CommentaryResponse
  // The commentary asked for. It differs from commentary.selected while another one is loading.
  requestedId: string
  onChangeCommentary: (commentaryId: string) => void
}

// Every line of the old texts is a paragraph or a point of an outline (none are wrapped by hand).
function paragraphsOf(text: string) {
  return text.split(/\n+/).filter((paragraph) => paragraph.trim() !== '')
}

function CommentaryPanel({ commentary, requestedId, onChangeCommentary }: CommentaryPanelProps) {
  const isLoading = commentary.selected !== requestedId
  const chosen = commentary.commentaries.find((entry) => entry.id === commentary.selected)

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
          <div className="commentary-text">
            {paragraphsOf(commentary.text).map((paragraph, index) => (
              <p key={index}>{paragraph}</p>
            ))}
          </div>
          {commentary.chapter_introduction && (
            <details className="commentary-introduction">
              <summary>
                Introduction to {commentary.book_name} {commentary.chapter}
              </summary>
              {paragraphsOf(commentary.chapter_introduction).map((paragraph, index) => (
                <p key={index}>{paragraph}</p>
              ))}
            </details>
          )}
          {commentary.book_introduction && (
            <details className="commentary-introduction">
              <summary>Introduction to {commentary.book_name}</summary>
              {paragraphsOf(commentary.book_introduction).map((paragraph, index) => (
                <p key={index}>{paragraph}</p>
              ))}
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
