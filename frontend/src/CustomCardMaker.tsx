import { useContext, useEffect, useMemo, useState } from 'react'
import {
  cardBackgroundAddress,
  fetchBibleChapter,
  fetchBibleContents,
  fetchCardBackgrounds,
  fetchCardRecipients,
  fetchCustomCard,
  sendCustomCard,
} from './api'
import type { CardBackground, CardVerse, DayCard } from './api'
import { AccountContext } from './AccountContext'
import type { BibleContents, BibleVerse, Translation } from './types'

interface CustomCardMakerProps {
  translations: Translation[]
}

// Where the maker starts: John 3:16 in the BSB (else the first Bible stored here).
const STARTING_VERSE = { book: 43, chapter: 3, verse: 16 }
const PLAIN = 'plain'

// Make your own card (added 2026-11-26 at the owner's request), at the foot of the Verse of the day page: choose
// a Bible stored on this site, a verse and a background (the verse a day pictures in use, as thumbnails, or plain
// blue), see the card, then download it, or (logged in) send it to a site user chosen by name or to an email
// address. The card is drawn on the server like the Verse of the day (custom_cards.py); sending draws it again
// there, so what is sent is what was shown.
function CustomCardMaker({ translations }: CustomCardMakerProps) {
  const { user, onNavigate } = useContext(AccountContext)
  const bibles = useMemo(() => translations.filter((translation) => translation.source === 'local'), [translations])
  // The Bible chosen; until one is, the BSB when it is here, else the first one.
  const [pickedTranslation, setTranslation] = useState('')
  const translation = pickedTranslation || (bibles.find((bible) => bible.code === 'BSB') ?? bibles[0])?.code || ''
  const [contents, setContents] = useState<BibleContents | null>(null)
  const [book, setBook] = useState(STARTING_VERSE.book)
  const [chapter, setChapter] = useState(STARTING_VERSE.chapter)
  const [verses, setVerses] = useState<BibleVerse[]>([])
  const [verse, setVerse] = useState(STARTING_VERSE.verse)
  const [backgrounds, setBackgrounds] = useState<CardBackground[]>([])
  const [background, setBackground] = useState(PLAIN)
  const [card, setCard] = useState<DayCard | null>(null)
  const [isDrawing, setIsDrawing] = useState(false)
  const [problem, setProblem] = useState('')

  useEffect(() => {
    fetchCardBackgrounds()
      .then((found) => {
        setBackgrounds(found)
        // Start on the first picture, when there is one.
        setBackground(found[0]?.id ?? PLAIN)
      })
      .catch(() => setBackgrounds([{ id: PLAIN, title: 'Plain blue', thumbnail: null }]))
  }, [])

  // The books and chapters of the Bible chosen; a Bible without the book starts at its first.
  useEffect(() => {
    if (!translation) {
      return
    }
    const controller = new AbortController()
    fetchBibleContents(translation, controller.signal)
      .then((found) => {
        setContents(found)
        if (!found.books.some((entry) => entry.number === book)) {
          setBook(found.books[0].number)
          setChapter(found.books[0].chapters[0])
          setVerse(1)
        }
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted) {
          setProblem(error.message)
        }
      })
    return () => controller.abort()
    // Only when the Bible changes: the book is checked against it then.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [translation])

  // The verses of the chapter, to choose from (each with its first words).
  useEffect(() => {
    if (!translation) {
      return
    }
    const controller = new AbortController()
    fetchBibleChapter(translation, book, chapter, controller.signal)
      .then((found) => {
        setVerses(found.verses)
        if (!found.verses.some((entry) => entry.verse === verse)) {
          setVerse(found.verses[0]?.verse ?? 1)
        }
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted) {
          setVerses([])
          setProblem(error.message)
        }
      })
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [translation, book, chapter])

  const chosen: CardVerse | null = translation && verses.some((entry) => entry.verse === verse)
    ? { translation, book, chapter, verse }
    : null

  // The preview, drawn again whenever a choice changes (a moment later, so quick changes make one picture).
  useEffect(() => {
    if (!chosen) {
      return
    }
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      setIsDrawing(true)
      fetchCustomCard(chosen, background, controller.signal)
        .then((found) => {
          setCard(found)
          setProblem('')
        })
        .catch((error: Error) => {
          if (!controller.signal.aborted) {
            setProblem(error.message)
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) {
            setIsDrawing(false)
          }
        })
    }, 250)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chosen?.translation, chosen?.book, chosen?.chapter, chosen?.verse, background])

  if (bibles.length === 0) {
    return null
  }
  const books = contents?.books ?? []
  const chapters = books.find((entry) => entry.number === book)?.chapters ?? []
  const fileName = card
    ? `${card.caption.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')}.jpg`
    : 'verse-card.jpg'

  return (
    <section className="custom-card" aria-labelledby="custom-card-heading">
      <h2 id="custom-card-heading">Make your own card</h2>
      <p>Choose a Bible, a verse and a background. Then download the card, or send it to someone.</p>

      <div className="custom-card-choices">
        <label>
          Bible
          <select value={translation} onChange={(event) => setTranslation(event.target.value)}>
            {bibles.map((bible) => (
              <option key={bible.code} value={bible.code}>
                {bible.name} ({bible.code})
              </option>
            ))}
          </select>
        </label>
        <label>
          Book
          <select
            value={book}
            onChange={(event) => {
              const number = Number(event.target.value)
              setBook(number)
              setChapter(books.find((entry) => entry.number === number)?.chapters[0] ?? 1)
              setVerse(1)
            }}
          >
            {books.map((entry) => (
              <option key={entry.number} value={entry.number}>
                {entry.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Chapter
          <select
            value={chapter}
            onChange={(event) => {
              setChapter(Number(event.target.value))
              setVerse(1)
            }}
          >
            {chapters.map((number) => (
              <option key={number} value={number}>
                {number}
              </option>
            ))}
          </select>
        </label>
        <label className="custom-card-verse">
          Verse
          <select value={verse} onChange={(event) => setVerse(Number(event.target.value))}>
            {verses.map((entry) => (
              <option key={entry.verse} value={entry.verse}>
                {entry.verse}: {entry.text.length > 70 ? `${entry.text.slice(0, 70)}…` : entry.text}
              </option>
            ))}
          </select>
        </label>
      </div>

      <fieldset className="custom-card-backgrounds">
        <legend>Background</legend>
        <div className="custom-card-thumbnails" role="radiogroup" aria-label="Background">
          {backgrounds.map((entry) => (
            <button
              key={entry.id}
              type="button"
              role="radio"
              aria-checked={background === entry.id}
              className={background === entry.id ? 'custom-card-thumbnail is-chosen' : 'custom-card-thumbnail'}
              title={entry.title}
              onClick={() => setBackground(entry.id)}
            >
              {entry.thumbnail ? (
                <img src={cardBackgroundAddress(entry.thumbnail)} alt={entry.title} loading="lazy" />
              ) : (
                <span className="custom-card-plain">Plain</span>
              )}
            </button>
          ))}
        </div>
      </fieldset>

      {problem && (
        <p className="error" role="alert">
          {problem}
        </p>
      )}

      {card && (
        <figure className={isDrawing ? 'day-card is-loading' : 'day-card'}>
          <img src={card.image} alt={`${card.words} ${card.caption}`} width={540} height={675} />
          <figcaption>{card.caption}</figcaption>
        </figure>
      )}
      {!card && isDrawing && <p>Making the card…</p>}

      {card && (
        <>
          <div className="note-actions day-card-actions">
            <a className="primary-button" href={card.image} download={fileName}>
              Download the card
            </a>
          </div>
          {user ? (
            chosen && <SendCard verse={chosen} background={background} caption={card.caption} />
          ) : (
            <p className="custom-card-login">
              To send the card to someone,{' '}
              <button type="button" className="link-button" onClick={() => onNavigate('login')}>
                log in
              </button>
              .
            </p>
          )}
        </>
      )}
    </section>
  )
}

interface SendCardProps {
  verse: CardVerse
  background: string
  caption: string
}

// Send the card: to a site user chosen by name (they get it the way they chose on My account: email, text or
// both), or to an email address typed in.
function SendCard({ verse, background, caption }: SendCardProps) {
  const { user } = useContext(AccountContext)
  const hasEmail = Boolean(user?.email)
  const [mode, setMode] = useState<'member' | 'email'>('member')
  const [people, setPeople] = useState<{ id: number; name: string }[]>([])
  const [filter, setFilter] = useState('')
  const [recipientId, setRecipientId] = useState(0)
  const [email, setEmail] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [message, setMessage] = useState('')
  const [problem, setProblem] = useState('')

  useEffect(() => {
    fetchCardRecipients()
      .then(setPeople)
      .catch((error: Error) => setProblem(error.message))
  }, [])

  const shown = filter.trim()
    ? people.filter((person) => person.name.toLowerCase().includes(filter.trim().toLowerCase()))
    : people

  async function send() {
    setMessage('')
    setProblem('')
    if (mode === 'member' && !recipientId) {
      setProblem('Choose who to send it to.')
      return
    }
    if (mode === 'email' && !email.trim()) {
      setProblem('Type the email address to send it to.')
      return
    }
    setIsSending(true)
    try {
      const sent = await sendCustomCard(verse, background, mode === 'member' ? { recipientId } : { email: email.trim() })
      const how = sent.ways.length === 2 ? 'by email and text' : `by ${sent.ways[0]}`
      setMessage(`The card of ${caption} was sent to ${sent.sent_to} ${how}.`)
    } catch (error) {
      setProblem((error as Error).message)
    } finally {
      setIsSending(false)
    }
  }

  return (
    <fieldset className="custom-card-send">
      <legend>Send the card</legend>
      <div className="custom-card-send-to">
        <label>
          <input type="radio" name="card-send-to" checked={mode === 'member'} onChange={() => setMode('member')} /> To
          someone on this site
        </label>
        <label>
          <input type="radio" name="card-send-to" checked={mode === 'email'} onChange={() => setMode('email')} /> To an
          email address
        </label>
      </div>
      {mode === 'member' ? (
        <div className="custom-card-send-fields">
          {people.length > 10 && (
            <label>
              Find a person
              <input type="search" value={filter} onChange={(event) => setFilter(event.target.value)} />
            </label>
          )}
          <label>
            Send to
            <select value={recipientId} onChange={(event) => setRecipientId(Number(event.target.value))}>
              <option value={0}>Choose a person…</option>
              {shown.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.name}
                </option>
              ))}
            </select>
          </label>
          <p className="field-hint">They get it the way they chose on their account: by email, text or both.</p>
        </div>
      ) : (
        <div className="custom-card-send-fields">
          <label>
            Email address
            <input
              type="email"
              value={email}
              autoComplete="off"
              onChange={(event) => setEmail(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault()
                  void send()
                }
              }}
            />
          </label>
        </div>
      )}
      <p className="field-hint">
        It says it is from you{hasEmail ? ', and replies to the email go to your own address' : ''}.
      </p>
      <div className="note-actions">
        <button type="button" className="primary-button" onClick={() => void send()} disabled={isSending}>
          {isSending ? 'Sending…' : 'Send the card'}
        </button>
      </div>
      {message && (
        <p className="success" role="status">
          {message}
        </p>
      )}
      {problem && (
        <p className="error" role="alert">
          {problem}
        </p>
      )}
    </fieldset>
  )
}

export default CustomCardMaker
