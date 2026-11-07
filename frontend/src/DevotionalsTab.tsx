import { useEffect, useRef, useState } from 'react'
import { fetchDevotionalContents, fetchDevotionalUnit } from './api'
import BackToTopButton from './BackToTop'
import ContextWindow from './ContextWindow'
import DevotionalEmailPanel from './DevotionalEmailPanel'
import { chooseContextTranslation } from './contextTranslation'
import DevotionalCredit from './DevotionalCredit'
import NoteText from './NoteText'
import type { DevotionalContents, DevotionalEntry, DevotionalInfo, Destination, Translation } from './types'
import { useBackToTop } from './useBackToTop'
import { chapterKey, useChapterStrip } from './useChapterStrip'
import type { StripChapter } from './useChapterStrip'
import { useReaderWindows } from './useReaderWindows'

interface DevotionalsTabProps {
  devotionals: DevotionalInfo[]
  translations: Translation[]
  isHidden: boolean
  // Where a followed link (a note's) asks the reader to open.
  destination: Destination | null
}

// A day or chapter as the reader scrolls through them. The reader's engine knows chapters of books, so
// a section is its "book" and a unit (a day or a chapter) is its "chapter".
interface Reading extends StripChapter {
  devotional: DevotionalInfo
  section: number
  section_title: string
  unit: number
  title: string
  entries: DevotionalEntry[]
}

interface Place {
  section: number
  unit: number
}

function today(): Place {
  const now = new Date()
  return { section: now.getMonth() + 1, unit: now.getDate() }
}

async function loadReading(devotional: string, section: number, unit: number, signal: AbortSignal): Promise<Reading> {
  const loaded = await fetchDevotionalUnit(devotional, section, unit, signal)
  const toNeighbour = (neighbour: { section: number; unit: number } | null) =>
    neighbour && { book_number: neighbour.section, chapter: neighbour.unit }
  return {
    ...loaded,
    book_number: loaded.section,
    chapter: loaded.unit,
    previous: toNeighbour(loaded.previous),
    next: toNeighbour(loaded.next),
  }
}

// Read the public-domain devotionals. Choose a devotional and the month and day (or the part and
// chapter) and the page goes there, a daily devotional starting at today. Scroll on in either
// direction to read the days or chapters before and after.
function DevotionalsTab({ devotionals, translations, isHidden, destination }: DevotionalsTabProps) {
  const [contents, setContents] = useState<DevotionalContents | null>(null)
  const [devotionalId, setDevotionalId] = useState('')
  const [markedUnit, setMarkedUnit] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  // A new session closes any open window: the reader has gone somewhere else.
  const [session, setSession] = useState<object>({})
  // Where the reader asked to go, so the choosers show it before the reading has arrived.
  const [goal, setGoal] = useState<Place | null>(null)
  const devotionalRef = useRef('')
  const pendingTarget = useRef<Place | null>(null)
  const hasStarted = useRef(false)

  const {
    chapters: readings,
    extending,
    errorMessage: stripErrorMessage,
    visibleChapter,
    start,
    scrollToTop,
    registerChapter,
    topSentinel,
    bottomSentinel,
  } = useChapterStrip<Reading>((section, unit, signal) => loadReading(devotionalRef.current, section, unit, signal))
  const windows = useReaderWindows(session)
  const windowIsOpen = windows.isOpen
  const contextTranslation = chooseContextTranslation(translations)
  const current = devotionals.find((entry) => entry.id === devotionalId)

  // Go to a day or chapter of a devotional. The place asked for is used when it exists; a devotional
  // with chapters starts at its first, and a daily one at the day asked for, else the first.
  async function go(newDevotionalId: string, wanted: Place | null) {
    setErrorMessage('')
    try {
      const loaded =
        contents?.devotional.id === newDevotionalId
          ? contents
          : await fetchDevotionalContents(newDevotionalId, new AbortController().signal)
      const section = loaded.sections.find((entry) => entry.number === wanted?.section) ?? loaded.sections[0]
      const unit = section.units.find((entry) => entry.number === wanted?.unit) ?? section.units[0]
      devotionalRef.current = newDevotionalId
      pendingTarget.current = { section: section.number, unit: unit.number }
      setContents(loaded)
      setDevotionalId(newDevotionalId)
      setGoal({ section: section.number, unit: unit.number })
      setSession({})
      setMarkedUnit('')
      await start(section.number, unit.number)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Could not load the devotional.')
    }
  }

  // A link to a reading (from a note): open the reader there. This comes before the start below, so the
  // tab does not start twice.
  useEffect(() => {
    if (destination?.kind !== 'devotional' || devotionals.length === 0) {
      return
    }
    hasStarted.current = true
    const id = devotionals.find((entry) => entry.id === destination.devotional)?.id ?? devotionals[0].id
    // Following a link is the reason to open the reader, so this is the place to do it.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    go(id, { section: destination.section, unit: destination.unit })
    // Only a new destination (or the devotionals arriving) matters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [destination, devotionals])

  // Start with the first devotional the first time the tab is shown: at today's date if it is daily.
  useEffect(() => {
    if (!isHidden && !hasStarted.current && devotionals.length > 0) {
      hasStarted.current = true
      go(devotionals[0].id, devotionals[0].kind === 'daily' ? today() : null)
    }
    // go only reads state that does not matter on the first call.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isHidden, devotionals])

  // Once the first reading of a visit is on screen, scroll to it.
  useEffect(() => {
    const target = pendingTarget.current
    const first = readings[0]
    if (target === null || readings.length !== 1 || first.section !== target.section || first.unit !== target.unit) {
      return
    }
    pendingTarget.current = null
    setMarkedUnit(chapterKey(first.section, first.unit))
    document.getElementById(`reading-${first.section}-${first.unit}`)?.scrollIntoView({ block: 'start' })
  }, [readings])

  const isScrolledDown = useBackToTop(isHidden, windowIsOpen, scrollToTop)

  const sections = contents?.sections ?? []
  const shownSection = visibleChapter?.book ?? goal?.section ?? sections[0]?.number ?? 0
  const shownUnit = visibleChapter?.chapter ?? goal?.unit ?? 1
  const unitChoices = sections.find((entry) => entry.number === shownSection)?.units ?? []
  const isDaily = current?.kind === 'daily'

  // Changing devotional keeps the day of a daily one; going to a daily one from the other kind
  // starts at today.
  function changeDevotional(newId: string) {
    const target = devotionals.find((entry) => entry.id === newId)
    if (target?.kind !== 'daily') {
      go(newId, null)
    } else {
      go(newId, isDaily ? { section: shownSection, unit: shownUnit } : today())
    }
  }

  function openReference(book: number, chapter: number, verse: number, shownText: string, trigger: HTMLElement) {
    windows.open(
      'context',
      { translation: contextTranslation, book_number: book, chapter, verse, reference: shownText },
      trigger,
    )
  }

  const currentView = windows.currentView

  return (
    <div className="browse-tab" hidden={isHidden}>
      <div className="browse-controls" hidden={windowIsOpen}>
        <label className="inline-label">
          Devotional
          <select
            aria-label="Devotional"
            value={devotionalId}
            disabled={devotionalId === ''}
            onChange={(event) => changeDevotional(event.target.value)}
          >
            {devotionals.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.name}
              </option>
            ))}
          </select>
        </label>
        <label className="inline-label">
          {isDaily ? 'Month' : 'Part'}
          <select
            aria-label={isDaily ? 'Month' : 'Part'}
            value={shownSection}
            disabled={devotionalId === ''}
            onChange={(event) => go(devotionalId, { section: Number(event.target.value), unit: isDaily ? shownUnit : 1 })}
          >
            {sections.map((entry) => (
              <option key={entry.number} value={entry.number}>
                {entry.title}
              </option>
            ))}
          </select>
        </label>
        <label className="inline-label">
          {isDaily ? 'Day' : 'Chapter'}
          <select
            aria-label={isDaily ? 'Day' : 'Chapter'}
            value={shownUnit}
            disabled={devotionalId === ''}
            onChange={(event) => go(devotionalId, { section: shownSection, unit: Number(event.target.value) })}
          >
            {unitChoices.map((entry) => (
              <option key={entry.number} value={entry.number}>
                {isDaily ? entry.number : entry.title}
              </option>
            ))}
          </select>
        </label>
        {isDaily && (
          <button type="button" className="primary-button" onClick={() => go(devotionalId, today())}>
            Today
          </button>
        )}
        <button type="button" className="browse-top-link" onClick={scrollToTop}>
          ↑ Back to top
        </button>
      </div>

      {current && contents && (
        <div hidden={windowIsOpen}>
          <DevotionalEmailPanel devotional={current} sections={contents.sections} currentSection={shownSection} currentUnit={shownUnit} />
        </div>
      )}

      {(errorMessage || stripErrorMessage) && <p className="error">{errorMessage || stripErrorMessage}</p>}
      {readings.length === 0 && !errorMessage && !stripErrorMessage && <p>Loading…</p>}

      {readings.length > 0 && (
        <div className="browse-reading" hidden={windowIsOpen}>
          <div className="browse-edge" ref={topSentinel}>
            {extending === 'previous'
              ? 'Loading the one before…'
              : readings[0].previous === null
                ? `This is the start of ${readings[0].devotional.name}.`
                : ''}
          </div>

          {readings.map((reading) => (
            <section
              key={chapterKey(reading.section, reading.unit)}
              className={chapterKey(reading.section, reading.unit) === markedUnit ? 'browse-chapter is-marked-reading' : 'browse-chapter'}
              id={`reading-${reading.section}-${reading.unit}`}
              ref={registerChapter(reading.section, reading.unit)}
            >
              <div className="browse-heading">
                <h2>{reading.title}</h2>
                <span className="browse-commentary-name">
                  {reading.devotional.name}
                  {reading.devotional.kind === 'chapters' ? ` · ${reading.section_title}` : ''}
                </span>
              </div>
              <div className="browse-note-links">
                <button
                  type="button"
                  className="link-button"
                  onClick={(event) =>
                    windows.open(
                      'note',
                      {
                        translation: contextTranslation,
                        // A reading is not a verse; the window is about its subject.
                        book_number: 0,
                        chapter: 0,
                        verse: 0,
                        reference: `${reading.title} (${reading.devotional.name})`,
                        subject: {
                          item_type: 'devotional',
                          source_code: reading.devotional.id,
                          section: reading.section,
                          unit: reading.unit,
                        },
                      },
                      event.currentTarget,
                    )
                  }
                >
                  Notes
                  <span className="visually-hidden"> on {reading.title}</span>
                </button>
              </div>
              {reading.entries.map((entry, index) => (
                <article key={index} className="devotional-entry">
                  {entry.heading && <h3>{entry.heading}</h3>}
                  <div className="commentary-text">
                    <NoteText text={entry.text} references={entry.references} terms={[]} translation={contextTranslation} onOpenReference={openReference} />
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
              ? 'Loading the next one…'
              : readings[readings.length - 1].next === null
                ? `This is the end of ${readings[0].devotional.name}.`
                : ''}
          </div>
          <p className="related-note">
            <DevotionalCredit devotional={readings[0].devotional} />
          </p>
        </div>
      )}

      <BackToTopButton isVisible={isScrolledDown && !windowIsOpen && readings.length > 0} onClick={scrollToTop} />

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

export default DevotionalsTab
