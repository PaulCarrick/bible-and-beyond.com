import { Fragment, useEffect, useLayoutEffect, useRef } from 'react'
import { highlight, highlightLinked } from './highlight'
import CommentaryPanel from './CommentaryPanel'
import LexiconPanel from './LexiconPanel'
import RelatedPanel from './RelatedPanel'
import WordsPanel from './WordsPanel'
import type {
  CommentaryResponse,
  ContextKind,
  LexiconEntry,
  OriginalWordsResponse,
  ParallelVerse,
  RelatedDirection,
  RelatedResponse,
  VerseContext,
  VerseTarget,
} from './types'

// Space kept free below the window for the options bar, the footer, and padding.
const heightBelowWindow = 185
const minimumBodyHeight = 200

// What one window shows: one of the seven kinds of answer, for one verse (or one Strong's number).
export interface WindowView {
  id: number
  kind: ContextKind
  target: VerseTarget
  direction: RelatedDirection
  // Only the answer that matches the kind is filled in.
  context: VerseContext | null
  parallel: ParallelVerse | null
  related: RelatedResponse | null
  words: OriginalWordsResponse | null
  lexicon: LexiconEntry | null
  commentary: CommentaryResponse | null
  // The commentary asked for (null for the first that has notes).
  commentaryId: string | null
  errorMessage: string
}

interface ContextWindowProps {
  view: WindowView
  // True when this window was opened from another one, so there is somewhere to go back to.
  canGoBack: boolean
  // Search words are shown in bold in the chosen verse only, so the passage stays easy to read.
  terms: string[]
  wholeWords: boolean
  onBack: () => void
  onClose: () => void
  onOpenVerse: (kind: ContextKind, target: VerseTarget) => void
  onChangeDirection: (direction: RelatedDirection) => void
  onChangeCommentary: (commentaryId: string) => void
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
    case 'words':
      return `Original words of ${reference}`
    case 'lexicon':
      return `Lexicon entry ${reference}`
    case 'commentary':
      return `Commentaries on ${reference}`
    default:
      return `${reference} in context`
  }
}

function ContextWindow({
  view,
  canGoBack,
  terms,
  wholeWords,
  onBack,
  onClose,
  onOpenVerse,
  onChangeDirection,
  onChangeCommentary,
}: ContextWindowProps) {
  const { kind, context, parallel, related, words, lexicon, commentary, errorMessage } = view
  const { translation, reference } = view.target
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
  const answers = { parallel, related, words, lexicon, commentary, context, chapter: context }
  const hasAnswer = answers[kind] !== null

  return (
    <section className="context-window" aria-label={describe(kind, reference)}>
      <header className="context-header">
        {canGoBack && (
          <button type="button" className="context-back" onClick={onBack}>
            ← Back
          </button>
        )}
        <h2>
          {kind === 'commentary' ? (
            <>Commentaries on {commentary ? `${commentary.book_name} ${commentary.chapter}:${commentary.verse}` : reference}</>
          ) : kind === 'words' ? (
            <>
              Original words of {words ? `${words.book_name} ${words.chapter}:${words.verse}` : reference}
            </>
          ) : kind === 'lexicon' ? (
            <>
              {lexicon ? `${lexicon.strong_code} ${lexicon.gloss}` : reference}
            </>
          ) : kind === 'related' ? (
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

        {context && context.verses.some((entry) => entry.links) && (
          <p className="word-link-hint">Choose a word to see the Hebrew or Greek word behind it.</p>
        )}

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
                  {entry.links
                    ? highlightLinked(
                        entry.text,
                        entry.is_target ? terms : [],
                        wholeWords,
                        entry.links,
                        (strongCode) =>
                          onOpenVerse('lexicon', {
                            translation,
                            book_number: context.book_number,
                            chapter: entry.chapter,
                            verse: entry.verse,
                            reference: strongCode,
                            strong_code: strongCode,
                          }),
                      )
                    : highlight(entry.text, entry.is_target ? terms : [], wholeWords)}
                </span>{' '}
              </Fragment>
            ))}
          </p>
        )}

        {related && (
          <RelatedPanel
            related={related}
            direction={view.direction}
            onChangeDirection={onChangeDirection}
            onOpenVerse={onOpenVerse}
          />
        )}

        {commentary && (
          <CommentaryPanel
            commentary={commentary}
            requestedId={view.commentaryId ?? commentary.selected}
            onChangeCommentary={onChangeCommentary}
          />
        )}

        {words && <WordsPanel words={words} translation={translation} onOpenVerse={onOpenVerse} />}

        {lexicon && <LexiconPanel entry={lexicon} translation={translation} onOpenVerse={onOpenVerse} />}

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
