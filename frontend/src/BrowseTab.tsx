import { useEffect, useRef, useState } from 'react'
import { fetchCommentaryChapter, fetchCommentaryContents } from './api'
import ContextWindow from './ContextWindow'
import BackToTopButton from './BackToTop'
import { chooseContextTranslation } from './contextTranslation'
import NoteText from './NoteText'
import type { CommentaryChapter, CommentaryContents, CommentaryNote, CommentarySource, Translation } from './types'
import { useBackToTop } from './useBackToTop'
import { chapterKey, useChapterStrip } from './useChapterStrip'
import { useReaderWindows } from './useReaderWindows'

interface BrowseTabProps {
  commentaries: CommentarySource[]
  translations: Translation[]
  isHidden: boolean
}

interface Target {
  book: number
  chapter: number
  verse: number | null
}

// The note of a chapter that covers a verse; else the last one before it, else the first.
function noteCovering(notes: CommentaryNote[], verse: number) {
  return (
    notes.find((note) => note.verse <= verse && verse <= (note.end_verse ?? Infinity)) ??
    [...notes].reverse().find((note) => note.verse <= verse) ??
    notes[0]
  )
}

function noteId(chapter: CommentaryChapter, note: CommentaryNote) {
  return `note-${chapterKey(chapter.book_number, chapter.chapter).replace(':', '-')}-${note.verse}`
}

// Read a commentary without searching. Choose a commentary and a book, chapter and verse and the page
// goes to that place; scroll up or down to read on past it, chapter after chapter and book after book.
function BrowseTab({ commentaries, translations, isHidden }: BrowseTabProps) {
  const [contents, setContents] = useState<CommentaryContents | null>(null)
  const [commentaryId, setCommentaryId] = useState('')
  const [verseText, setVerseText] = useState('')
  // The note the reader asked for, shown with a mark.
  const [markedNote, setMarkedNote] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  // A new session closes any open window: the reader has gone somewhere else.
  const [session, setSession] = useState<object>({})
  // Where the reader asked to go, so the choosers show it before the chapter has arrived.
  const [goal, setGoal] = useState<{ book: number; chapter: number } | null>(null)
  const commentaryRef = useRef('')
  const pendingTarget = useRef<Target | null>(null)
  const hasStarted = useRef(false)

  const {
    chapters,
    extending,
    errorMessage: stripErrorMessage,
    visibleChapter,
    start,
    scrollToTop,
    registerChapter,
    topSentinel,
    bottomSentinel,
  } = useChapterStrip<CommentaryChapter>((book, chapter, signal) =>
    fetchCommentaryChapter(commentaryRef.current, book, chapter, signal),
  )
  const windows = useReaderWindows(session)
  const contextTranslation = chooseContextTranslation(translations)
  const windowIsOpen = windows.isOpen

  // Go to a place in a commentary. The same place is used when the commentary changes, so the same
  // passage can be compared in another commentary; a commentary without it starts at its nearest.
  async function go(newCommentaryId: string, wanted: Target) {
    setErrorMessage('')
    try {
      const loaded =
        contents?.commentary.id === newCommentaryId
          ? contents
          : await fetchCommentaryContents(newCommentaryId, new AbortController().signal)
      const book = loaded.books.find((entry) => entry.number === wanted.book) ?? loaded.books[0]
      const sameBook = book.number === wanted.book
      const chapter = sameBook && book.chapters.includes(wanted.chapter) ? wanted.chapter : book.chapters[0]
      const verse = sameBook && chapter === wanted.chapter ? wanted.verse : null
      commentaryRef.current = newCommentaryId
      pendingTarget.current = { book: book.number, chapter, verse }
      setContents(loaded)
      setCommentaryId(newCommentaryId)
      setGoal({ book: book.number, chapter })
      setSession({})
      setMarkedNote('')
      setVerseText(verse === null ? '' : String(verse))
      await start(book.number, chapter)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Could not load the commentary.')
    }
  }

  // Start with the first commentary the first time the tab is shown, so nothing is fetched for
  // visitors who never open it.
  useEffect(() => {
    if (!isHidden && !hasStarted.current && commentaries.length > 0) {
      hasStarted.current = true
      go(commentaries[0].id, { book: 1, chapter: 1, verse: null })
    }
    // go only reads state that does not matter on the first call.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isHidden, commentaries])

  // Once the first chapter of a visit is on screen, scroll to the place asked for.
  useEffect(() => {
    const target = pendingTarget.current
    const first = chapters[0]
    if (target === null || chapters.length !== 1 || first.book_number !== target.book || first.chapter !== target.chapter) {
      return
    }
    pendingTarget.current = null
    let element: HTMLElement | null = null
    if (target.verse !== null) {
      const note = noteCovering(first.entries, target.verse)
      setMarkedNote(noteId(first, note))
      element = document.getElementById(noteId(first, note))
    }
    element ??= document.getElementById(`chapter-${first.book_number}-${first.chapter}`)
    element?.scrollIntoView({ block: 'start' })
  }, [chapters])

  const isScrolledDown = useBackToTop(isHidden, windowIsOpen, scrollToTop)

  const books = contents?.books ?? []
  const shownBook = visibleChapter?.book ?? goal?.book ?? books[0]?.number ?? 0
  const shownChapter = visibleChapter?.chapter ?? goal?.chapter ?? 1
  const chapterChoices = books.find((entry) => entry.number === shownBook)?.chapters ?? []
  // The verse asked for still counts when the reader is still on its chapter: switching commentary
  // then shows the same verse in the other commentary.
  const askedVerse = Number.parseInt(verseText, 10)
  const verseToKeep =
    goal?.book === shownBook && goal.chapter === shownChapter && !Number.isNaN(askedVerse) && askedVerse > 0
      ? askedVerse
      : null

  function openWindow(
    chapter: CommentaryChapter,
    kind: 'context' | 'commentary',
    book: number,
    chapterNumber: number,
    verse: number,
    reference: string,
    trigger: HTMLElement,
  ) {
    windows.open(
      kind,
      { translation: contextTranslation, book_number: book, chapter: chapterNumber, verse, reference },
      trigger,
      { commentaryId: kind === 'commentary' ? chapter.commentary.id : null },
    )
  }

  function submitVerse(event: React.FormEvent) {
    event.preventDefault()
    const verse = Number.parseInt(verseText, 10)
    go(commentaryId, { book: shownBook, chapter: shownChapter, verse: Number.isNaN(verse) || verse < 1 ? null : verse })
  }

  const currentView = windows.currentView

  return (
    <div className="browse-tab" hidden={isHidden}>
      <div className="browse-controls" hidden={windowIsOpen}>
        <label className="inline-label">
          Commentary
          <select
            aria-label="Commentary"
            value={commentaryId}
            disabled={commentaryId === ''}
            onChange={(event) => go(event.target.value, { book: shownBook, chapter: shownChapter, verse: verseToKeep })}
          >
            {commentaries.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.name}
              </option>
            ))}
          </select>
        </label>
        <label className="inline-label">
          Book
          <select
            aria-label="Book"
            value={shownBook}
            disabled={commentaryId === ''}
            onChange={(event) => go(commentaryId, { book: Number(event.target.value), chapter: 1, verse: null })}
          >
            {books.map((entry) => (
              <option key={entry.number} value={entry.number}>
                {entry.name}
              </option>
            ))}
          </select>
        </label>
        <label className="inline-label">
          Chapter
          <select
            aria-label="Chapter"
            value={shownChapter}
            disabled={commentaryId === ''}
            onChange={(event) => go(commentaryId, { book: shownBook, chapter: Number(event.target.value), verse: null })}
          >
            {chapterChoices.map((number) => (
              <option key={number} value={number}>
                {number}
              </option>
            ))}
          </select>
        </label>
        <form className="inline-label browse-verse" onSubmit={submitVerse}>
          <label>
            Verse
            <input
              type="number"
              min={1}
              inputMode="numeric"
              aria-label="Verse"
              value={verseText}
              placeholder="any"
              onChange={(event) => setVerseText(event.target.value)}
            />
          </label>
          <button type="submit" className="primary-button" disabled={commentaryId === ''}>
            Go
          </button>
        </form>
        <button type="button" className="browse-top-link" onClick={scrollToTop}>
          ↑ Back to top
        </button>
      </div>

      {(errorMessage || stripErrorMessage) && <p className="error">{errorMessage || stripErrorMessage}</p>}
      {chapters.length === 0 && !errorMessage && !stripErrorMessage && <p>Loading…</p>}

      {chapters.length > 0 && (
        <div className="browse-reading" hidden={windowIsOpen}>
          <div className="browse-edge" ref={topSentinel}>
            {extending === 'previous'
              ? 'Loading the chapter before…'
              : chapters[0].previous === null
                ? `This is the start of ${chapters[0].commentary.name}.`
                : ''}
          </div>

          {chapters.map((chapter) => (
            <section
              key={chapterKey(chapter.book_number, chapter.chapter)}
              className="browse-chapter"
              id={`chapter-${chapter.book_number}-${chapter.chapter}`}
              ref={registerChapter(chapter.book_number, chapter.chapter)}
            >
              <div className="browse-heading">
                <h2>
                  {chapter.book_name} {chapter.chapter}
                </h2>
                <span className="browse-commentary-name">{chapter.commentary.name}</span>
              </div>

              {chapter.book_introduction && (
                <details className="commentary-introduction">
                  <summary>Introduction to {chapter.book_name}</summary>
                  <NoteText
                    text={chapter.book_introduction}
                    references={chapter.book_introduction_references}
                    terms={[]}
                    onOpenReference={(book, chapterNumber, verse, shown, trigger) =>
                      openWindow(chapter, 'context', book, chapterNumber, verse, shown, trigger)
                    }
                  />
                </details>
              )}
              {chapter.chapter_introduction && (
                <details className="commentary-introduction" open>
                  <summary>
                    Introduction to {chapter.book_name} {chapter.chapter}
                  </summary>
                  <NoteText
                    text={chapter.chapter_introduction}
                    references={chapter.chapter_introduction_references}
                    terms={[]}
                    onOpenReference={(book, chapterNumber, verse, shown, trigger) =>
                      openWindow(chapter, 'context', book, chapterNumber, verse, shown, trigger)
                    }
                  />
                </details>
              )}

              {chapter.entries.map((note) => (
                <article
                  key={note.verse}
                  id={noteId(chapter, note)}
                  className={noteId(chapter, note) === markedNote ? 'browse-note is-marked' : 'browse-note'}
                >
                  <h3>{note.covers}</h3>
                  <div className="browse-note-links">
                    <button
                      type="button"
                      className="link-button"
                      onClick={(event) =>
                        openWindow(chapter, 'context', chapter.book_number, chapter.chapter, note.verse, note.covers, event.currentTarget)
                      }
                    >
                      Show in Context
                      <span className="visually-hidden"> for {note.covers}</span>
                    </button>
                    <button
                      type="button"
                      className="link-button"
                      onClick={(event) =>
                        openWindow(chapter, 'commentary', chapter.book_number, chapter.chapter, note.verse, note.covers, event.currentTarget)
                      }
                    >
                      Other Commentaries
                      <span className="visually-hidden"> on {note.covers}</span>
                    </button>
                    <button
                      type="button"
                      className="link-button"
                      onClick={(event) =>
                        windows.open(
                          'note',
                          {
                            translation: contextTranslation,
                            book_number: chapter.book_number,
                            chapter: chapter.chapter,
                            verse: note.verse,
                            reference: `${note.covers} (${chapter.commentary.short_name})`,
                            subject: {
                              item_type: 'commentary',
                              source_code: chapter.commentary.id,
                              book_number: chapter.book_number,
                              chapter: chapter.chapter,
                              verse: note.verse,
                            },
                          },
                          event.currentTarget,
                        )
                      }
                    >
                      Notes
                      <span className="visually-hidden"> on {note.covers}</span>
                    </button>
                  </div>
                  <div className="commentary-text">
                    <NoteText
                      text={note.text}
                      references={note.references}
                      terms={[]}
                      onOpenReference={(book, chapterNumber, verse, shown, trigger) =>
                        openWindow(chapter, 'context', book, chapterNumber, verse, shown, trigger)
                      }
                    />
                  </div>
                </article>
              ))}
            </section>
          ))}

          <div className="browse-to-top">
            <button type="button" className="link-button" onClick={scrollToTop}>
              ↑ Back to top
            </button>
          </div>

          <div className="browse-edge" ref={bottomSentinel}>
            {extending === 'next'
              ? 'Loading the next chapter…'
              : chapters[chapters.length - 1].next === null
                ? `This is the end of ${chapters[0].commentary.name}.`
                : ''}
          </div>
        </div>
      )}

      <BackToTopButton isVisible={isScrolledDown && !windowIsOpen && chapters.length > 0} onClick={scrollToTop} />

      {windowIsOpen && currentView && (
        <ContextWindow
          key={currentView.id}
          view={currentView}
          canGoBack={windows.views.length > 1}
          terms={[]}
          wholeWords={false}
          onBack={windows.goBack}
          onClose={windows.close}
          onOpenVerse={windows.openVerse}
          onChangeDirection={windows.changeDirection}
          onChangeCommentary={windows.changeCommentary}
        />
      )}
    </div>
  )
}

export default BrowseTab
