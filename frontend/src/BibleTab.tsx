import { useEffect, useRef, useState } from 'react'
import { fetchBibleChapter, fetchBibleContents } from './api'
import BackToTopButton from './BackToTop'
import ContextWindow from './ContextWindow'
import { highlightLinked } from './highlight'
import VerseMenu from './VerseMenu'
import type { VerseMenuItem } from './VerseMenu'
import type { BibleChapter, BibleContents, BibleVerse, ContextKind, Destination, Translation } from './types'
import { useBackToTop } from './useBackToTop'
import { chapterKey, useChapterStrip } from './useChapterStrip'
import { useReaderWindows } from './useReaderWindows'

interface BibleTabProps {
  translations: Translation[]
  isHidden: boolean
  // Where a followed link (a note's) asks the reader to open.
  destination: Destination | null
}

interface Target {
  book: number
  chapter: number
  verse: number | null
}

// What the verse menu offers: the same things as the links under a search result.
const verseMenuItems: VerseMenuItem[] = [
  { kind: 'context', label: 'Show in Context', opensVerse: true },
  { kind: 'chapter', label: 'Full Chapter', opensVerse: true },
  { kind: 'parallel', label: 'Other Translations' },
  { kind: 'related', label: 'Related Verses' },
  { kind: 'words', label: 'Original Words' },
  { kind: 'commentary', label: 'Commentaries' },
  { kind: 'note', label: 'Notes' },
]

function verseId(chapter: BibleChapter, verse: BibleVerse) {
  return `verse-${chapter.book_number}-${chapter.chapter}-${verse.verse}`
}

// Read a Bible stored on this site. Choose a Bible and a book, chapter and verse and the page goes
// there; scroll up or down to read on past it, chapter after chapter and book after book. A verse has
// a menu (right-click it, or click its number) with the same things as the links of a search result.
function BibleTab({ translations, isHidden, destination }: BibleTabProps) {
  const [contents, setContents] = useState<BibleContents | null>(null)
  const [translationCode, setTranslationCode] = useState('')
  const [verseText, setVerseText] = useState('')
  // The verse the reader asked for, shown with a mark.
  const [markedVerse, setMarkedVerse] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  // A new session closes any open window: the reader has gone somewhere else.
  const [session, setSession] = useState<object>({})
  // Where the reader asked to go, so the choosers show it before the chapter has arrived.
  const [goal, setGoal] = useState<{ book: number; chapter: number } | null>(null)
  // The verse menu: which verse it is for and where it opened.
  const [menu, setMenu] = useState<{ chapter: BibleChapter; verse: BibleVerse; x: number; y: number } | null>(null)
  const translationRef = useRef('')
  const pendingTarget = useRef<Target | null>(null)
  // A Strong's number a link asked for: its lexicon entry opens over the verse once the verse is on screen.
  const pendingStrongCode = useRef<string | null>(null)
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
  } = useChapterStrip<BibleChapter>((book, chapter, signal) =>
    fetchBibleChapter(translationRef.current, book, chapter, signal),
  )
  const windows = useReaderWindows(session)
  const windowIsOpen = windows.isOpen
  // Only Bibles stored on this site can be read a chapter at a time.
  const readable = translations.filter((translation) => translation.source === 'local')

  // Go to a place in a Bible. The same place is used when the Bible changes, so the same passage can
  // be compared in another Bible; a Bible without it starts at its nearest.
  async function go(newTranslationCode: string, wanted: Target) {
    setErrorMessage('')
    try {
      const loaded =
        contents?.translation.code === newTranslationCode
          ? contents
          : await fetchBibleContents(newTranslationCode, new AbortController().signal)
      const book = loaded.books.find((entry) => entry.number === wanted.book) ?? loaded.books[0]
      const sameBook = book.number === wanted.book
      const chapter = sameBook && book.chapters.includes(wanted.chapter) ? wanted.chapter : book.chapters[0]
      const verse = sameBook && chapter === wanted.chapter ? wanted.verse : null
      translationRef.current = newTranslationCode
      pendingTarget.current = { book: book.number, chapter, verse }
      setContents(loaded)
      setTranslationCode(newTranslationCode)
      setGoal({ book: book.number, chapter })
      setSession({})
      setMarkedVerse('')
      setVerseText(verse === null ? '' : String(verse))
      await start(book.number, chapter)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Could not load the Bible.')
    }
  }

  // A link to a verse (from a note): open the reader there, in the Bible the note was written in when it
  // can be read here, else the BSB. This comes before the start below, so the tab does not start twice.
  useEffect(() => {
    if (destination?.kind !== 'bible' || readable.length === 0) {
      return
    }
    hasStarted.current = true
    pendingStrongCode.current = destination.strongCode ?? null
    const code =
      (readable.find((translation) => translation.code === destination.translation) ??
        readable.find((translation) => translation.code === 'BSB') ??
        readable[0]).code
    // Following a link is the reason to open the reader, so this is the place to do it.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    go(code, { book: destination.book, chapter: destination.chapter, verse: destination.verse })
    // Only a new destination (or the Bibles arriving) matters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [destination, translations])

  // Start with the BSB (else the first Bible) the first time the tab is shown.
  useEffect(() => {
    if (!isHidden && !hasStarted.current && readable.length > 0) {
      hasStarted.current = true
      const first = readable.find((translation) => translation.code === 'BSB') ?? readable[0]
      go(first.code, { book: 1, chapter: 1, verse: null })
    }
    // go only reads state that does not matter on the first call.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isHidden, translations])

  // Once the first chapter of a visit is on screen, scroll to the place asked for.
  useEffect(() => {
    const target = pendingTarget.current
    const first = chapters[0]
    if (target === null || chapters.length !== 1 || first.book_number !== target.book || first.chapter !== target.chapter) {
      return
    }
    pendingTarget.current = null
    let element: HTMLElement | null = null
    let markedEntry: BibleVerse | null = null
    if (target.verse !== null) {
      // A verse the Bible does not have (a number past the end) goes to the chapter's last verse.
      const verse = first.verses.find((entry) => entry.verse >= (target.verse ?? 0)) ?? first.verses[first.verses.length - 1]
      markedEntry = verse
      setMarkedVerse(verseId(first, verse))
      element = document.getElementById(verseId(first, verse))
    }
    element ??= document.getElementById(`chapter-${first.book_number}-${first.chapter}`)
    element?.scrollIntoView({ block: 'start' })
    // A link that names a Strong's number (the FAQ's Greek words) opens its lexicon entry over the verse;
    // Back or the X returns to the verse.
    const strongCode = pendingStrongCode.current
    pendingStrongCode.current = null
    if (strongCode && markedEntry) {
      const trigger = numberButton(first, markedEntry) ?? element
      if (trigger) {
        openStrongNumber(first, markedEntry, strongCode, trigger)
      }
    }
    // openStrongNumber only reads the windows, which do not change what this does.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapters])

  const isScrolledDown = useBackToTop(isHidden, windowIsOpen, scrollToTop)

  const books = contents?.books ?? []
  const shownBook = visibleChapter?.book ?? goal?.book ?? books[0]?.number ?? 0
  const shownChapter = visibleChapter?.chapter ?? goal?.chapter ?? 1
  const chapterChoices = books.find((entry) => entry.number === shownBook)?.chapters ?? []
  // The verse asked for still counts when the reader is still on its chapter: switching Bible then
  // shows the same verse in the other Bible.
  const askedVerse = Number.parseInt(verseText, 10)
  const verseToKeep =
    goal?.book === shownBook && goal.chapter === shownChapter && !Number.isNaN(askedVerse) && askedVerse > 0
      ? askedVerse
      : null

  function openWindow(chapter: BibleChapter, verse: BibleVerse, kind: ContextKind, trigger: HTMLElement) {
    windows.open(
      kind,
      {
        translation: chapter.translation.code,
        book_number: chapter.book_number,
        chapter: chapter.chapter,
        verse: verse.verse,
        reference: `${chapter.book_name} ${chapter.chapter}:${verse.verse}`,
      },
      trigger,
    )
  }

  // The verse number is the verse's one focusable part: it opens the menu for a tap or a keyboard,
  // and is where the focus goes back to when the menu or a window closes.
  function numberButton(chapter: BibleChapter, verse: BibleVerse) {
    return document.getElementById(`${verseId(chapter, verse)}-number`)
  }

  // Right-click on a verse. A selection of text or a Shift-click keeps the browser's own menu, so
  // copying still works.
  function handleContextMenu(event: React.MouseEvent<HTMLElement>, chapter: BibleChapter, verse: BibleVerse) {
    if (event.shiftKey || (window.getSelection()?.toString() ?? '') !== '') {
      return
    }
    event.preventDefault()
    let { clientX: x, clientY: y } = event
    if (x === 0 && y === 0) {
      // From the keyboard (the menu key) there is no pointer: open at the verse number.
      const box = numberButton(chapter, verse)?.getBoundingClientRect()
      x = box?.left ?? 0
      y = box?.bottom ?? 0
    }
    setMenu({ chapter, verse, x, y })
  }

  function closeMenu() {
    if (menu) {
      numberButton(menu.chapter, menu.verse)?.focus({ preventScroll: true })
    }
    setMenu(null)
  }

  function chooseFromMenu(kind: ContextKind) {
    if (menu === null) {
      return
    }
    const trigger = numberButton(menu.chapter, menu.verse)
    setMenu(null)
    if (trigger) {
      openWindow(menu.chapter, menu.verse, kind, trigger)
    }
  }

  // A word of the BSB was chosen: open the lexicon entry of the Hebrew or Greek word behind it.
  function openStrongNumber(chapter: BibleChapter, verse: BibleVerse, strongCode: string, trigger: HTMLElement) {
    windows.open(
      'lexicon',
      {
        translation: chapter.translation.code,
        book_number: chapter.book_number,
        chapter: chapter.chapter,
        verse: verse.verse,
        reference: strongCode,
        strong_code: strongCode,
      },
      trigger,
    )
  }

  function submitVerse(event: React.FormEvent) {
    event.preventDefault()
    const verse = Number.parseInt(verseText, 10)
    go(translationCode, { book: shownBook, chapter: shownChapter, verse: Number.isNaN(verse) || verse < 1 ? null : verse })
  }

  const currentView = windows.currentView

  return (
    <div className="browse-tab" hidden={isHidden}>
      <div className="browse-controls" hidden={windowIsOpen}>
        <label className="inline-label">
          Bible
          <select
            aria-label="Bible"
            value={translationCode}
            disabled={translationCode === ''}
            onChange={(event) => go(event.target.value, { book: shownBook, chapter: shownChapter, verse: verseToKeep })}
          >
            {readable.map((translation) => (
              <option key={translation.code} value={translation.code}>
                {translation.name} ({translation.code})
              </option>
            ))}
          </select>
        </label>
        <label className="inline-label">
          Book
          <select
            aria-label="Book"
            value={shownBook}
            disabled={translationCode === ''}
            onChange={(event) => go(translationCode, { book: Number(event.target.value), chapter: 1, verse: null })}
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
            disabled={translationCode === ''}
            onChange={(event) => go(translationCode, { book: shownBook, chapter: Number(event.target.value), verse: null })}
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
          <button type="submit" className="primary-button" disabled={translationCode === ''}>
            Go
          </button>
        </form>
        <button type="button" className="browse-top-link" onClick={scrollToTop}>
          ↑ Back to top
        </button>
      </div>

      {(errorMessage || stripErrorMessage) && <p className="error">{errorMessage || stripErrorMessage}</p>}
      {chapters.length > 0 && !windowIsOpen && (
        <p className="reader-hint">
          Right-click a verse, or click its number, for Show in Context, Other Translations, Related Verses and more.
        </p>
      )}
      {chapters.length === 0 && !errorMessage && !stripErrorMessage && <p>Loading…</p>}

      {chapters.length > 0 && (
        <div className="browse-reading" hidden={windowIsOpen}>
          <div className="browse-edge" ref={topSentinel}>
            {extending === 'previous'
              ? 'Loading the chapter before…'
              : chapters[0].previous === null
                ? `This is the start of the ${chapters[0].translation.name}.`
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
                <span className="browse-commentary-name">{chapter.translation.name}</span>
              </div>

              {chapter.verses.map((verse) => (
                <div
                  key={verse.verse}
                  id={verseId(chapter, verse)}
                  className={
                    verseId(chapter, verse) === markedVerse
                      ? 'bible-verse is-marked'
                      : menu?.chapter === chapter && menu.verse === verse
                        ? 'bible-verse is-menu-target'
                        : 'bible-verse'
                  }
                  onContextMenu={(event) => handleContextMenu(event, chapter, verse)}
                >
                  <p className="bible-verse-text" lang={chapter.translation.language}>
                    <button
                      type="button"
                      id={`${verseId(chapter, verse)}-number`}
                      className="verse-number-button"
                      aria-haspopup="menu"
                      title="More for this verse: right-click it, or click its number. Show in Context, Full Chapter, Other Translations, Related Verses, Original Words, Commentaries and Notes."
                      onClick={(event) => {
                        const box = event.currentTarget.getBoundingClientRect()
                        setMenu({ chapter, verse, x: box.left, y: box.bottom })
                      }}
                    >
                      <sup className="verse-number">{verse.verse}</sup>
                      <span className="visually-hidden">
                        {' '}
                        Options for {chapter.book_name} {chapter.chapter}:{verse.verse}
                      </span>
                    </button>
                    {verse.links
                      ? highlightLinked(verse.text, [], false, verse.links, (code, element) =>
                          openStrongNumber(chapter, verse, code, element),
                        )
                      : verse.text}
                  </p>
                </div>
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
                ? `This is the end of the ${chapters[0].translation.name}.`
                : ''}
          </div>
        </div>
      )}

      {menu && !windowIsOpen && (
        <VerseMenu
          x={menu.x}
          y={menu.y}
          heading={`${menu.chapter.book_name} ${menu.chapter.chapter}:${menu.verse.verse}`}
          items={verseMenuItems}
          verse={{
            translation: menu.chapter.translation.code,
            book: menu.chapter.book_number,
            chapter: menu.chapter.chapter,
            verse: menu.verse.verse,
          }}
          onChoose={chooseFromMenu}
          onClose={closeMenu}
        />
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

export default BibleTab
