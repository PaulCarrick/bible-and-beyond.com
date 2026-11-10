import { useContext, useEffect, useRef, useState } from 'react'
import { AccountContext } from './AccountContext'
import { fetchFaqAnswer, fetchFaqQuestions } from './api'
import type { FaqAnswer, FaqListing } from './api'
import FaqAnswerView from './FaqAnswerView'
import FaqOwnerNote from './FaqOwnerNote'
import OpenQuestionBox from './OpenQuestionBox'

interface FaqPageProps {
  isHidden: boolean
  // A question to show when the page opens, from an address such as /faq?question=... (a link in a note
  // from the site owner opened in a new tab).
  initialQuestion?: string | null
}

// Common questions about the faith, answered by Google's Gemini. Only the listed questions can be asked; the
// server keeps each answer for a day, and the page keeps the ones it has shown so going back is instant.
function FaqPage({ isHidden, initialQuestion = null }: FaqPageProps) {
  const { user } = useContext(AccountContext)
  const [listing, setListing] = useState<FaqListing | null>(null)
  const [listingErrorMessage, setListingErrorMessage] = useState('')
  const [questionId, setQuestionId] = useState(1)
  const [answers, setAnswers] = useState<Record<number, FaqAnswer>>({})
  const [shownQuestionId, setShownQuestionId] = useState<number | null>(null)
  const [isAsking, setIsAsking] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')

  // The list is loaded the first time the page is opened.
  useEffect(() => {
    if (isHidden || listing) {
      return
    }
    fetchFaqQuestions()
      .then((loaded) => {
        setListing(loaded)
        setListingErrorMessage('')
      })
      .catch(() => setListingErrorMessage('The questions could not be loaded. Please try again later.'))
  }, [isHidden, listing])

  function ask(askedId: number = questionId) {
    setErrorMessage('')
    if (answers[askedId]) {
      setShownQuestionId(askedId)
      return
    }
    setIsAsking(true)
    setShownQuestionId(null)
    fetchFaqAnswer(askedId)
      .then((answer) => {
        setAnswers((earlier) => ({ ...earlier, [askedId]: answer }))
        setShownQuestionId(askedId)
      })
      .catch((error: Error) => setErrorMessage(error.message))
      .finally(() => setIsAsking(false))
  }

  // Another question's answer, asked for from a link in the page (the owner's note points to the one on grace).
  function showQuestion(question: string) {
    const entry = listing?.groups.flatMap((group) => group.questions).find((candidate) => candidate.question === question)
    if (!entry) {
      return
    }
    setQuestionId(entry.id)
    ask(entry.id)
    window.scrollTo(0, 0)
  }

  // The question an address asked for, shown once the list has arrived.
  const initialQuestionShown = useRef(false)
  useEffect(() => {
    if (!listing?.available || !initialQuestion || initialQuestionShown.current) {
      return
    }
    initialQuestionShown.current = true
    showQuestion(initialQuestion)
    // showQuestion is a new function on every render; this runs once, when the list arrives.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listing, initialQuestion])

  const shownAnswer = shownQuestionId === null ? null : answers[shownQuestionId]
  const isAvailable = listing?.available ?? false

  return (
    <div className="welcome faq-page" hidden={isHidden}>
      <h1>Frequently asked questions</h1>
      <p>
        Choose a question about God, Jesus, the Bible or the Christian life and press <em>Show the answer</em>. The
        answers are written by an AI (Google Gemini) from a Bible-centred, historic Christian point of view, with
        Scripture references you can look up. Where Christians disagree, it tries to describe the main views fairly.
      </p>

      {listingErrorMessage && <p className="error">{listingErrorMessage}</p>}
      {!listing && !listingErrorMessage && <p>Loading the questions…</p>}

      {listing && (
        <>
          {!isAvailable && (
            <p className="error" role="status">
              The FAQ answers are not available right now. Please try again later.
            </p>
          )}
          <div className="faq-controls">
            <label className="field-label" htmlFor="faq-question">
              Question
            </label>
            <select
              id="faq-question"
              className="faq-select"
              value={questionId}
              onChange={(event) => setQuestionId(Number(event.target.value))}
            >
              {listing.groups.map((group) => (
                <optgroup key={group.heading} label={group.heading}>
                  {group.questions.map((entry) => (
                    <option key={entry.id} value={entry.id}>
                      {entry.question}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            <button type="button" className="primary-button" onClick={() => ask()} disabled={!isAvailable || isAsking}>
              {isAsking ? 'Asking…' : 'Show the answer'}
            </button>
          </div>
        </>
      )}

      <div aria-live="polite">
        {isAsking && <p className="faq-waiting">Writing the answer. This can take up to half a minute…</p>}
        {errorMessage && <p className="error">{errorMessage}</p>}
        {shownAnswer && !isAsking && (
          <FaqAnswerView question={shownAnswer.question} answer={shownAnswer.answer} references={shownAnswer.references}>
            {shownAnswer.owner_note && <FaqOwnerNote html={shownAnswer.owner_note} onShowQuestion={showQuestion} />}
          </FaqAnswerView>
        )}
      </div>

      {/* Only for a logged-in account an administrator allowed (open_ai_queries); hidden for everyone else. */}
      {user?.open_ai_queries && isAvailable && <OpenQuestionBox />}
    </div>
  )
}

export default FaqPage
