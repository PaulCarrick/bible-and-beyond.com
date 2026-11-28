import { useCallback, useEffect, useState } from 'react'
import type { MouseEvent, ReactNode } from 'react'
import { fetchDayCard } from './api'
import type { DayCard } from './api'
import CustomCardMaker from './CustomCardMaker'
import type { Translation } from './types'
import { verseAddress, wantsNewTab } from './verseAddress'
import type { VerseInBible } from './verseAddress'

interface DayCardPageProps {
  kind: 'verse' | 'devotional'
  // The Bibles, for Make your own card (Verse of the day only).
  translations: Translation[]
  onOpenVerse: (verse: VerseInBible) => void
  onOpenReading: (devotional: string, section: number, unit: number) => void
}

// Verse of the day and Devotional of the day (the sidebar's Today group; added 2026-11-16 at the owner's
// request): a picture made the same way as the picture messages (message_cards.py on the server: the words in
// a large script over a random verse a day picture), with Download and a button to read it in full. The verse
// is chosen at random each time; the devotional is today's reading of a daily devotional chosen at random (the
// evening reading from 5 pm). Show another asks for a new one. The picture comes inline (a data: address), so
// Download saves exactly what is shown. On the verse, the picture and its reference are links to the verse in the
// Bible reader (2026-11-16, the owner's request): a plain click opens it here, Ctrl, Cmd or the middle button a
// new tab, as any link.
// On the verse page the two parts are sections that open and close (2026-11-28, the owner's request): Verse of
// the day starts open and Make your own card closed; opening one closes the other, and a click on the open one's
// heading closes it. Both stay mounted (the closed one hidden), so the picture is fetched at once and the maker
// keeps its choices while closed. The page is mounted only while shown, so each visit starts on Verse of the day.
type VerseSection = 'verse' | 'card' | null

function DayCardPage({ kind, translations, onOpenVerse, onOpenReading }: DayCardPageProps) {
  const [card, setCard] = useState<DayCard | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [request, setRequest] = useState(0)
  const [openSection, setOpenSection] = useState<VerseSection>('verse')

  const load = useCallback(
    (signal: AbortSignal) => {
      fetchDayCard(kind, signal)
        .then((found) => {
          setCard(found)
          setErrorMessage('')
        })
        .catch((error: Error) => {
          if (!signal.aborted) {
            setErrorMessage(error.message)
          }
        })
        .finally(() => {
          if (!signal.aborted) {
            setIsLoading(false)
          }
        })
    },
    [kind],
  )

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
    return () => controller.abort()
  }, [load, request])

  function showAnother() {
    setIsLoading(true)
    setRequest((count) => count + 1)
  }

  const title = kind === 'verse' ? 'Verse of the day' : 'Devotional of the day'
  const fileName = kind === 'verse' ? 'verse-of-the-day.jpg' : 'devotional-of-the-day.jpg'
  const reading = card?.reading
  const verse = card?.verse

  // The picture or the reference as a link to the verse, when there is one.
  function linkToVerse(content: ReactNode, label: string) {
    if (!verse) {
      return content
    }
    return (
      <a
        href={verseAddress(verse.translation, verse.book, verse.chapter, verse.verse)}
        title={label}
        onClick={(event: MouseEvent<HTMLAnchorElement>) => {
          if (!wantsNewTab(event)) {
            event.preventDefault()
            onOpenVerse(verse)
          }
        }}
      >
        {content}
      </a>
    )
  }

  const dayCard = (
    <>
      <p className="day-card-intro">
        {kind === 'verse'
          ? 'A well-known Bible verse, chosen at random, on a picture you can download and share.'
          : 'A reading for today from one of the daily devotionals, on a picture you can download and share.'}
      </p>
      {errorMessage && (
        <p className="error" role="alert">
          {errorMessage}
        </p>
      )}
      {card && (
        <figure className={isLoading ? 'day-card is-loading' : 'day-card'}>
          {linkToVerse(
            <img src={card.image} alt={`${card.words} ${card.caption}`} width={540} height={675} />,
            `Read ${card.caption} in the Bible`,
          )}
          <figcaption>
            {reading
              ? `${reading.name}, ${reading.title}${reading.heading ? ` (${reading.heading})` : ''}`
              : linkToVerse(card.caption, `Read ${card.caption} in the Bible`)}
          </figcaption>
        </figure>
      )}
      {!card && isLoading && <p>Making the picture…</p>}
      {card && (
        <div className="note-actions day-card-actions">
          <a className="primary-button" href={card.image} download={fileName}>
            Download the picture
          </a>
          <button type="button" className="secondary-button" onClick={showAnother} disabled={isLoading}>
            {isLoading ? 'Making another…' : 'Show another'}
          </button>
          {card.verse && (
            <button type="button" className="secondary-button" onClick={() => card.verse && onOpenVerse(card.verse)}>
              Read it in the Bible
            </button>
          )}
          {reading && (
            <button
              type="button"
              className="secondary-button"
              onClick={() => onOpenReading(reading.devotional, reading.section, reading.unit)}
            >
              Read the whole reading
            </button>
          )}
        </div>
      )}
    </>
  )

  if (kind !== 'verse') {
    return (
      <div className="day-card-page">
        <h1>{title}</h1>
        {dayCard}
      </div>
    )
  }

  // One heading button of the verse page's sections, with the sidebar's small triangle.
  function sectionHeading(section: 'verse' | 'card', label: string) {
    const isOpen = openSection === section
    return (
      <h2 className="day-card-section-heading">
        <button
          type="button"
          aria-expanded={isOpen}
          aria-controls={`day-card-section-${section}`}
          onClick={() => setOpenSection(isOpen ? null : section)}
        >
          <span className="side-nav-arrow" aria-hidden="true">
            ▶
          </span>
          {label}
        </button>
      </h2>
    )
  }

  return (
    <div className="day-card-page">
      <h1>{title}</h1>
      {sectionHeading('verse', 'Verse of the day')}
      <div id="day-card-section-verse" className="day-card-section" hidden={openSection !== 'verse'}>
        {dayCard}
      </div>
      {sectionHeading('card', 'Make your own card')}
      <div id="day-card-section-card" className="day-card-section" hidden={openSection !== 'card'}>
        <CustomCardMaker translations={translations} showHeading={false} />
      </div>
    </div>
  )
}

export default DayCardPage
