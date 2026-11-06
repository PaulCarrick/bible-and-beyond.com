import { Fragment } from 'react'
import CrossReferenceCredit from './CrossReferenceCredit'
import type { ContextKind, RelatedDirection, RelatedResponse, VerseTarget } from './types'

interface RelatedPanelProps {
  related: RelatedResponse
  // The direction asked for. It differs from related.direction while the other list is loading.
  direction: RelatedDirection
  onChangeDirection: (direction: RelatedDirection) => void
  onOpenVerse: (kind: ContextKind, target: VerseTarget) => void
}

const emptyMessages: Record<RelatedDirection, string> = {
  from: 'This verse has no cross references to other verses.',
  to: 'No other verse has a cross reference to this one.',
}

function RelatedPanel({ related, direction, onChangeDirection, onOpenVerse }: RelatedPanelProps) {
  const isLoading = related.direction !== direction
  const tabs: { direction: RelatedDirection; label: string; count: number }[] = [
    { direction: 'from', label: 'Points to', count: related.outgoing_total },
    { direction: 'to', label: 'Pointed to by', count: related.incoming_total },
  ]

  return (
    <>
      <div className="related-tabs" role="group" aria-label="Which cross references to show">
        {tabs.map((tab) => (
          <button
            type="button"
            key={tab.direction}
            className="related-tab"
            aria-pressed={direction === tab.direction}
            onClick={() => onChangeDirection(tab.direction)}
          >
            {tab.label} ({tab.count.toLocaleString()})
          </button>
        ))}
      </div>

      {isLoading ? (
        <p>Loading…</p>
      ) : (
        <>
          {related.references.length === 0 && <p>{emptyMessages[related.direction]}</p>}
          <ol className="related-list">
            {related.references.map((entry) => {
              const target: VerseTarget = {
                translation: related.translation,
                book_number: entry.book_number,
                chapter: entry.chapter,
                verse: entry.verse,
                reference: entry.reference,
              }
              return (
                <li key={`${entry.book_number}-${entry.chapter}-${entry.verse}`} className="related-item">
                  <div className="related-head">
                    <strong className="related-reference">{entry.reference}</strong>
                    <span className="related-votes">
                      {entry.votes.toLocaleString()} {entry.votes === 1 ? 'vote' : 'votes'}
                    </span>
                  </div>
                  {entry.verses.length === 0 ? (
                    <p className="related-missing">This verse is not in {related.translation}.</p>
                  ) : (
                    <p className="related-text">
                      {entry.verses.map((verse, index) => (
                        <Fragment key={`${verse.chapter}-${verse.verse}`}>
                          {entry.verses.length > 1 && (
                            <sup className="verse-number">
                              {index > 0 && verse.chapter !== entry.verses[index - 1].chapter
                                ? `${verse.chapter}:${verse.verse}`
                                : verse.verse}
                            </sup>
                          )}
                          {verse.text}{' '}
                        </Fragment>
                      ))}
                      {entry.has_more_verses && <span className="related-more">…</span>}
                    </p>
                  )}
                  <div className="related-actions">
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => onOpenVerse('context', target)}
                    >
                      Show in Context
                      <span className="visually-hidden"> for {entry.reference}</span>
                    </button>
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => onOpenVerse('related', target)}
                    >
                      Related Verses
                      <span className="visually-hidden"> for {entry.reference}</span>
                    </button>
                  </div>
                </li>
              )
            })}
          </ol>
          <p className="related-note">
            {related.total > related.shown
              ? `Showing the ${related.shown} best-voted of ${related.total.toLocaleString()} verses. `
              : ''}
            Votes rank how useful the link is. <CrossReferenceCredit />
          </p>
        </>
      )}
    </>
  )
}

export default RelatedPanel
