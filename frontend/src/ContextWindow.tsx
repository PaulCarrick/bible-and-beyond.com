import { Fragment, useEffect, useLayoutEffect, useRef } from 'react'
import CrossReferenceCredit from './CrossReferenceCredit'
import { highlight } from './highlight'
import type { ContextKind, ParallelVerse, RelatedResponse, VerseContext } from './types'

// Space kept free below the window for the options bar, the footer, and padding.
const heightBelowWindow = 185
const minimumBodyHeight = 200

interface ContextWindowProps {
  kind: ContextKind
  translation: string
  reference: string
  // The answer for Show in Context or Full Chapter, for Other Translations, or for Related Verses.
  // Only the one that matches the kind is filled in.
  context: VerseContext | null
  parallel: ParallelVerse | null
  related: RelatedResponse | null
  errorMessage: string
  // Search words are shown in bold in the chosen verse only, so the passage stays easy to read.
  terms: string[]
  wholeWords: boolean
  onClose: () => void
}

function formatTitle(kind: ContextKind, context: VerseContext) {
  if (kind === 'chapter') {
    return `${context.book_name} ${context.chapter}`
  }
  const first = context.verses[0]
  const last = context.verses[context.verses.length - 1]
  if (first.chapter !== last.chapter) {
    return `${context.book_name} ${first.chapter}:${first.verse} – ${last.chapter}:${last.verse}`
  }
  if (first.verse === last.verse) {
    return `${context.book_name} ${first.chapter}:${first.verse}`
  }
  return `${context.book_name} ${first.chapter}:${first.verse}–${last.verse}`
}

function describe(kind: ContextKind, reference: string) {
  switch (kind) {
    case 'chapter':
      return `Full chapter for ${reference}`
    case 'parallel':
      return `Other translations of ${reference}`
    case 'related':
      return `Verses related to ${reference}`
    default:
      return `${reference} in context`
  }
}

function ContextWindow({
  kind,
  translation,
  reference,
  context,
  parallel,
  related,
  errorMessage,
  terms,
  wholeWords,
  onClose,
}: ContextWindowProps) {
  const closeButton = useRef<HTMLButtonElement>(null)
  const body = useRef<HTMLDivElement>(null)
  const targetVerse = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    closeButton.current?.focus()
  }, [])

  // Keep the window inside the browser window: it scrolls on its own instead of the page.
  useLayoutEffect(() => {
    function fitToWindow() {
      const element = body.current
      if (element === null) {
        return
      }
      const footer = document.querySelector('.site-footer')
      const footerHeight = footer ? footer.getBoundingClientRect().height : 0
      const top = element.getBoundingClientRect().top + window.scrollY
      const available = window.innerHeight - top - heightBelowWindow - footerHeight
      element.style.maxHeight = `${Math.max(minimumBodyHeight, available)}px`
    }
    fitToWindow()
    window.addEventListener('resize', fitToWindow)
    return () => window.removeEventListener('resize', fitToWindow)
  }, [])

  // Show the chosen verse in the middle of the window once the text has arrived.
  useEffect(() => {
    if (context && body.current && targetVerse.current) {
      const bodyBox = body.current.getBoundingClientRect()
      const verseBox = targetVerse.current.getBoundingClientRect()
      body.current.scrollTop += verseBox.top - bodyBox.top - bodyBox.height / 2 + verseBox.height / 2
    }
  }, [context])

  const showChapters = context !== null && new Set(context.verses.map((entry) => entry.chapter)).size > 1
  // The Bible that was searched comes first, then the rest in order of code.
  const parallelTranslations = parallel
    ? [
        ...parallel.translations.filter((entry) => entry.code === translation),
        ...parallel.translations.filter((entry) => entry.code !== translation),
      ]
    : []
  const hasAnswer = kind === 'parallel' ? parallel !== null : kind === 'related' ? related !== null : context !== null

  return (
    <section className="context-window" aria-label={describe(kind, reference)}>
      <header className="context-header">
        <h2>
          {kind === 'related' ? (
            <>
              Related to {related ? `${related.book_name} ${related.chapter}:${related.verse}` : reference}
              <span className="translation-code"> {translation}</span>
            </>
          ) : kind === 'parallel' ? (
            <>
              {parallel ? `${parallel.book_name} ${parallel.chapter}:${parallel.verse}` : reference}
              <span className="translation-code"> in {parallel ? parallel.translations.length : '…'} Bibles</span>
            </>
          ) : (
            <>
              {context ? formatTitle(kind, context) : reference}
              <span className="translation-code"> {translation}</span>
            </>
          )}
        </h2>
        <button
          type="button"
          ref={closeButton}
          className="context-close"
          aria-label="Close and go back to the results"
          onClick={onClose}
        >
          ✕
        </button>
      </header>

      <div className="context-body" ref={body}>
        {errorMessage && <p className="error">{errorMessage}</p>}
        {!hasAnswer && !errorMessage && <p>Loading…</p>}

        {context && (
          <p className="context-text">
            {context.verses.map((entry, index) => (
              <Fragment key={`${entry.chapter}-${entry.verse}`}>
                {showChapters && (index === 0 || entry.chapter !== context.verses[index - 1].chapter) && (
                  <span className="context-chapter">Chapter {entry.chapter}</span>
                )}
                <span
                  ref={entry.is_target ? targetVerse : undefined}
                  className={entry.is_target ? 'context-verse target' : 'context-verse'}
                >
                  <sup className="verse-number">{entry.verse}</sup>
                  {highlight(entry.text, entry.is_target ? terms : [], wholeWords)}
                </span>{' '}
              </Fragment>
            ))}
          </p>
        )}

        {related && (
          <>
            {related.references.length === 0 && <p>No related verses were found for this verse.</p>}
            <ol className="related-list">
              {related.references.map((entry) => (
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
                </li>
              ))}
            </ol>
            <p className="related-note">
              {related.total > related.shown
                ? `Showing the ${related.shown} best-voted of ${related.total} related verses. `
                : ''}
              Votes rank how useful the link is. <CrossReferenceCredit />
            </p>
          </>
        )}

        {parallel && (
          <>
            <dl className="parallel-list">
              {parallelTranslations.map((entry) => (
                <div
                  key={entry.code}
                  className={entry.code === translation ? 'parallel-row current' : 'parallel-row'}
                  lang={entry.language}
                >
                  <dt>
                    <span className="parallel-code">{entry.code}</span>
                    <span className="parallel-name">{entry.name}</span>
                    {entry.code === translation && <span className="parallel-current">This result</span>}
                  </dt>
                  <dd>{highlight(entry.text, entry.code === translation ? terms : [], wholeWords)}</dd>
                </div>
              ))}
            </dl>
            <p className="parallel-note">
              Only the Bibles stored on this site are shown. The NIV, NASB and The Message are not included.
            </p>
          </>
        )}
      </div>
    </section>
  )
}

export default ContextWindow
