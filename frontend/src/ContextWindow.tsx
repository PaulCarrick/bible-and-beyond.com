import { Fragment, useEffect, useLayoutEffect, useRef } from 'react'
import { highlight } from './highlight'
import type { VerseContext } from './types'

// Space kept free below the window for the options bar, the footer, and padding.
const heightBelowWindow = 185
const minimumBodyHeight = 200

interface ContextWindowProps {
  translation: string
  reference: string
  context: VerseContext | null
  errorMessage: string
  // Search words are shown in bold in the chosen verse only, so the passage stays easy to read.
  terms: string[]
  wholeWords: boolean
  onClose: () => void
}

function formatRange(context: VerseContext) {
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

function ContextWindow({
  translation,
  reference,
  context,
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

  return (
    <section className="context-window" aria-label={`${reference} in context`}>
      <header className="context-header">
        <h2>
          {context ? formatRange(context) : reference}
          <span className="translation-code"> {translation}</span>
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
        {!context && !errorMessage && <p>Loading…</p>}
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
      </div>
    </section>
  )
}

export default ContextWindow
