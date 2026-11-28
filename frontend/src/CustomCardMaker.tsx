import { useContext, useEffect, useId, useMemo, useRef, useState } from 'react'
import {
  cardBackgroundAddress,
  fetchBibleChapter,
  fetchBibleContents,
  fetchCardBackgrounds,
  fetchCardRecipients,
  fetchCustomCard,
  saveCustomCard,
  sendCustomCard,
} from './api'
import type { CardBackground, CardToSend, CardVerse, DayCard, SavedCard } from './api'
import { AccountContext } from './AccountContext'
import RichTextEditor from './RichTextEditor'
import type { RichTextEditorHandle } from './RichTextEditor'
import type { BibleContents, BibleVerse, Translation } from './types'

interface CustomCardMakerProps {
  translations: Translation[]
  // A saved card being edited (My cards' Edit): the maker starts on it, and saving, downloading or sending the
  // card replaces it.
  editing?: SavedCard
  // A card was kept on My cards (downloaded, sent or saved).
  onSaved?: (card: SavedCard) => void
  // Edit only: back to the list (Cancel, or after Save changes).
  onClose?: () => void
  // False inside the Verse of the day page's sections, whose heading button already says "Make your own card".
  showHeading?: boolean
}

// Where the maker starts: John 3:16 in the BSB (else the first Bible stored here).
const STARTING_VERSE = { book: 43, chapter: 3, verse: 16 }
const PLAIN = 'plain'

// Make your own card (added 2026-11-26 at the owner's request), the second section of the Verse of the day page: choose
// a Bible stored on this site, a verse and a background (the verse a day pictures in use, as thumbnails, or plain
// blue), see the card, then download it, or (logged in) send it to a site user chosen by name or to an email
// address. The card is drawn on the server like the Verse of the day (custom_cards.py); sending draws it again
// there, so what is sent is what was shown. A logged-in member's card is kept on My cards whenever they download or
// send it (saved_cards.py; the owner's request, 2026-11-26), and My cards opens it here again to edit it.
// "Add my own message" (the owner's request, 2026-11-28), beside the verse: a rich text editor whose words take the
// place of the verse's on the card (the reference stays under them); the server cleans the HTML.
function CustomCardMaker({ translations, editing, onSaved, onClose, showHeading = true }: CustomCardMakerProps) {
  const { user, onNavigate } = useContext(AccountContext)
  const bibles = useMemo(() => translations.filter((translation) => translation.source === 'local'), [translations])
  // The Bible chosen; until one is, the BSB when it is here, else the first one.
  const [pickedTranslation, setTranslation] = useState(editing?.translation ?? '')
  const translation = pickedTranslation || (bibles.find((bible) => bible.code === 'BSB') ?? bibles[0])?.code || ''
  const [contents, setContents] = useState<BibleContents | null>(null)
  const [book, setBook] = useState(editing?.book ?? STARTING_VERSE.book)
  const [chapter, setChapter] = useState(editing?.chapter ?? STARTING_VERSE.chapter)
  const [verses, setVerses] = useState<BibleVerse[]>([])
  const [verse, setVerse] = useState(editing?.verse ?? STARTING_VERSE.verse)
  const [backgrounds, setBackgrounds] = useState<CardBackground[]>([])
  const [background, setBackground] = useState(editing?.background ?? PLAIN)
  // What happened to the card on My cards ("Kept on My cards."), and whether it is being saved.
  const [keptMessage, setKeptMessage] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [card, setCard] = useState<DayCard | null>(null)
  const [isDrawing, setIsDrawing] = useState(false)
  const [problem, setProblem] = useState('')
  // "Add my own message": whether it is ticked, and the message as HTML from the editor ('' while it is empty).
  const [hasOwnMessage, setHasOwnMessage] = useState(Boolean(editing?.message_html))
  const [messageHtml, setMessageHtml] = useState(editing?.message_html ?? '')
  const messageEditorReference = useRef<RichTextEditorHandle>(null)
  const messageLabelId = useId()
  // The message the card is drawn with: none until something is written, or when the box is unticked.
  const ownMessage = hasOwnMessage && messageHtml ? messageHtml : undefined

  // When the editor opens, it starts with the message written so far (or the saved card's, when editing).
  useEffect(() => {
    if (hasOwnMessage && messageHtml) {
      messageEditorReference.current?.setHtml(messageHtml)
    }
    // Only when the box is ticked: while typing, the editor holds the message itself.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasOwnMessage])

  useEffect(() => {
    fetchCardBackgrounds()
      .then((found) => {
        setBackgrounds(found)
        // Start on the first picture, when there is one (a card being edited keeps its own).
        if (!editing) {
          setBackground(found[0]?.id ?? PLAIN)
        }
      })
      .catch(() => setBackgrounds([{ id: PLAIN, title: 'Plain blue', thumbnail: null }]))
    // Once, when the maker opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  // The preview, drawn again whenever a choice changes (a moment later, so quick changes make one picture; a little
  // longer while a message is being typed).
  useEffect(() => {
    if (!chosen) {
      return
    }
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      setIsDrawing(true)
      fetchCustomCard(chosen, background, controller.signal, ownMessage)
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
    }, ownMessage ? 600 : 250)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chosen?.translation, chosen?.book, chosen?.chapter, chosen?.verse, background, ownMessage])

  // Keeps the card shown on My cards (downloading it, or Save changes when editing).
  async function keepCard(): Promise<boolean> {
    if (!user || !chosen) {
      return false
    }
    setIsSaving(true)
    try {
      const kept = await saveCustomCard(chosen, background, editing?.id, ownMessage)
      setKeptMessage(editing ? 'Your changes were saved on My cards.' : 'Saved on My cards.')
      onSaved?.(kept)
      return true
    } catch (error) {
      setKeptMessage(`It could not be kept on My cards: ${(error as Error).message}`)
      return false
    } finally {
      setIsSaving(false)
    }
  }

  if (bibles.length === 0) {
    return null
  }
  const books = contents?.books ?? []
  const chapters = books.find((entry) => entry.number === book)?.chapters ?? []
  const fileName = card
    ? `${card.caption.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')}.jpg`
    : 'verse-card.jpg'

  return (
    <section
      className={showHeading ? 'custom-card' : 'custom-card is-in-section'}
      aria-labelledby={showHeading ? 'custom-card-heading' : undefined}
    >
      {showHeading && <h2 id="custom-card-heading">{editing ? 'Edit your card' : 'Make your own card'}</h2>}
      <p>
        {editing
          ? 'Change the Bible, the verse, your message or the background. Save changes, download or send it, and your card on My cards is changed to match.'
          : 'Choose a Bible, a verse and a background, or write your own message in place of the verse. Then download the card, or send it to someone.'}
        {!editing && user && ' Save it to My cards to keep it; every card you download or send is kept there too.'}
      </p>

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
            {editing && (
              <button
                type="button"
                className="primary-button"
                disabled={isSaving || isDrawing}
                onClick={() => {
                  void keepCard().then((saved) => {
                    if (saved) {
                      onClose?.()
                    }
                  })
                }}
              >
                {isSaving ? 'Saving…' : 'Save changes'}
              </button>
            )}
            {!editing && user && (
              // Keeps the card without downloading or sending it (the owner's request, 2026-11-26).
              <button
                type="button"
                className="secondary-button"
                disabled={isSaving || isDrawing}
                onClick={() => void keepCard()}
              >
                {isSaving ? 'Saving…' : 'Save to My cards'}
              </button>
            )}
            <a
              className={editing ? 'secondary-button' : 'primary-button'}
              href={card.image}
              download={fileName}
              onClick={() => void keepCard()}
            >
              Download the card
            </a>
            {editing && (
              <button type="button" className="secondary-button" onClick={onClose}>
                Cancel
              </button>
            )}
          </div>
          {keptMessage && (
            <p className="field-hint" role="status">
              {keptMessage}
            </p>
          )}
        </>
      )}

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
        <label className="custom-card-own-message">
          <input
            type="checkbox"
            checked={hasOwnMessage}
            onChange={(event) => setHasOwnMessage(event.target.checked)}
          />{' '}
          Add my own message
        </label>
      </div>

      {hasOwnMessage && (
        <div className="custom-card-message">
          <p id={messageLabelId} className="field-hint">
            Your message takes the place of the verse's words on the card; the reference stays under it. Up to 500
            characters. A new line in your message starts a new line on the card.
          </p>
          <RichTextEditor
            ref={messageEditorReference}
            placeholder="Write your message here"
            labelledBy={messageLabelId}
            onChange={() => {
              const editor = messageEditorReference.current
              setMessageHtml(editor && !editor.isEmpty() ? editor.getHtml() : '')
            }}
          />
        </div>
      )}

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

      {card && (
        <>
          {user ? (
            chosen && (
              <SendCard
                card={{ verse: chosen, background, cardId: editing?.id, message: ownMessage }}
                caption={card.caption}
                onSent={(kept) => {
                  if (kept) {
                    setKeptMessage(editing ? 'Your changes were saved on My cards.' : 'It is kept on My cards.')
                    onSaved?.(kept)
                  }
                }}
              />
            )
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
  card: CardToSend
  caption: string
  // The card as kept on My cards after it went (null when it could not be kept).
  onSent?: (card: SavedCard | null) => void
}

// Send the card: to a site user chosen by name (they get it the way they chose on My account: email, text or
// both), or to an email address typed in.
export function SendCard({ card, caption, onSent }: SendCardProps) {
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
  const radioName = useId()

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
      const sent = await sendCustomCard(card, mode === 'member' ? { recipientId } : { email: email.trim() })
      const how = sent.ways.length === 2 ? 'by email and text' : `by ${sent.ways[0]}`
      setMessage(`The card of ${caption} was sent to ${sent.sent_to} ${how}.`)
      onSent?.(sent.card)
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
          <input type="radio" name={radioName} checked={mode === 'member'} onChange={() => setMode('member')} /> To
          someone on this site
        </label>
        <label>
          <input type="radio" name={radioName} checked={mode === 'email'} onChange={() => setMode('email')} /> To an
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
