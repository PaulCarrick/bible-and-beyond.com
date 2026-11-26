import { useContext, useEffect, useState } from 'react'
import { deleteSavedCard, fetchSavedCards, savedCardAddress, savedCardPicture } from './api'
import type { SavedCard } from './api'
import { AccountContext } from './AccountContext'
import CustomCardMaker, { SendCard } from './CustomCardMaker'
import type { Translation } from './types'
import type { View } from './views'

interface MyCardsPageProps {
  translations: Translation[]
  onNavigate: (view: View) => void
}

// My cards (in the account icon's menu, after My lists; the owner's request, 2026-11-26): every verse card the
// member downloaded or sent from Make your own card (saved_cards.py), newest first, each with Edit (the card maker
// opens on it; saving changes that card), Download, Send and Delete, as in the maker.
function MyCardsPage({ translations, onNavigate }: MyCardsPageProps) {
  const { user } = useContext(AccountContext)
  const [cards, setCards] = useState<SavedCard[] | null>(null)
  const [problem, setProblem] = useState('')
  const [editing, setEditing] = useState<SavedCard | null>(null)
  // The card whose Send box is open, and the one asked "delete it?".
  const [sendingId, setSendingId] = useState(0)
  const [confirmingId, setConfirmingId] = useState(0)

  function load() {
    fetchSavedCards()
      .then((found) => {
        setCards(found)
        setProblem('')
      })
      .catch((error: Error) => setProblem(error.message))
  }

  useEffect(() => {
    if (user) {
      load()
    }
  }, [user])

  async function download(card: SavedCard) {
    try {
      const picture = await savedCardPicture(card)
      const address = URL.createObjectURL(picture)
      const link = document.createElement('a')
      link.href = address
      link.download = `${card.caption.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')}.jpg`
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(address), 10000)
    } catch (error) {
      setProblem((error as Error).message)
    }
  }

  async function remove(card: SavedCard) {
    try {
      await deleteSavedCard(card.id)
      setConfirmingId(0)
      setCards((current) => (current ?? []).filter((each) => each.id !== card.id))
    } catch (error) {
      setProblem((error as Error).message)
    }
  }

  if (!user) {
    return (
      <div className="welcome my-cards">
        <h1>My cards</h1>
        <p>
          Your verse cards are kept here when you are logged in.{' '}
          <button type="button" className="link-button" onClick={() => onNavigate('login')}>
            Log in
          </button>
        </p>
      </div>
    )
  }

  if (editing) {
    return (
      <div className="welcome my-cards">
        <h1>My cards</h1>
        <CustomCardMaker
          key={editing.id}
          translations={translations}
          editing={editing}
          onSaved={(kept) => setEditing(kept)}
          onClose={() => {
            setEditing(null)
            load()
          }}
        />
      </div>
    )
  }

  return (
    <div className="welcome my-cards">
      <h1>My cards</h1>
      <p>
        The cards you save, download or send from <em>Make your own card</em> are kept here, newest first. Edit one to change
        its verse or background.{' '}
        <button type="button" className="link-button" onClick={() => onNavigate('verseOfTheDay')}>
          Make a new card
        </button>
      </p>
      {problem && (
        <p className="error" role="alert">
          {problem}
        </p>
      )}
      {cards === null && !problem && <p>Loading…</p>}
      {cards?.length === 0 && <p>You have no cards yet.</p>}
      <ul className="my-cards-list">
        {(cards ?? []).map((card) => (
          <li key={card.id} className="my-card">
            <img
              src={savedCardAddress(card.thumbnail)}
              alt={`${card.words} ${card.caption}`}
              width={240}
              height={300}
              loading="lazy"
            />
            <div className="my-card-details">
              <p className="my-card-caption">{card.caption}</p>
              <p className="field-hint">
                {new Date(card.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}
              </p>
              <div className="note-actions">
                <button type="button" className="secondary-button" onClick={() => setEditing(card)}>
                  Edit
                </button>
                <button type="button" className="secondary-button" onClick={() => void download(card)}>
                  Download
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  aria-expanded={sendingId === card.id}
                  onClick={() => setSendingId(sendingId === card.id ? 0 : card.id)}
                >
                  Send
                </button>
                <button type="button" className="secondary-button" onClick={() => setConfirmingId(card.id)}>
                  Delete
                </button>
              </div>
              {confirmingId === card.id && (
                <p className="my-card-confirm">
                  Delete this card?{' '}
                  <button type="button" className="secondary-button small-button danger-button" onClick={() => void remove(card)}>
                    Yes, delete it
                  </button>{' '}
                  <button type="button" className="secondary-button small-button" onClick={() => setConfirmingId(0)}>
                    Cancel
                  </button>
                </p>
              )}
              {sendingId === card.id && <SendCard card={{ savedCardId: card.id }} caption={card.caption} />}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default MyCardsPage
