import { useEffect, useState } from 'react'
import { answerMessagePermission, fetchMessageRequests } from './api'
import type { MessagePermission } from './types'

interface MessageRequestsBoxProps {
  // Whether the Conversations page is shown (the requests are asked for when it is).
  isHidden: boolean
  // After an answer: the page lists its posts again (an accepted sender's posts now show).
  onAnswered: () => void
}

// The member's waiting requests at the top of Conversations (2026-11-23): someone would like to send them posts to
// them alone. Accept shows those posts and every later one; Decline stops that person sending them posts. Either
// can be changed on My account.
function MessageRequestsBox({ isHidden, onAnswered }: MessageRequestsBoxProps) {
  const [requests, setRequests] = useState<MessagePermission[]>([])
  const [busySender, setBusySender] = useState<number | null>(null)
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(() => {
    if (isHidden) {
      return
    }
    const controller = new AbortController()
    fetchMessageRequests(controller.signal)
      .then(setRequests)
      .catch(() => setRequests([]))
    return () => controller.abort()
  }, [isHidden])

  async function answer(senderId: number, accept: boolean) {
    setBusySender(senderId)
    setErrorMessage('')
    try {
      await answerMessagePermission(senderId, accept)
      setRequests((waiting) => waiting.filter((request) => request.sender_id !== senderId))
      onAnswered()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Your answer could not be saved.')
    } finally {
      setBusySender(null)
    }
  }

  if (requests.length === 0) {
    return null
  }
  return (
    <section className="message-requests" aria-labelledby="message-requests-heading">
      <h2 id="message-requests-heading">Requests to send you posts</h2>
      <ul>
        {requests.map((request) => (
          <li key={request.sender_id}>
            <p>
              <strong>{request.sender}</strong> would like to send you posts that only the two of you see. Nothing they
              wrote shows until you accept.
            </p>
            <div className="note-actions">
              <button type="button" className="primary-button" disabled={busySender !== null} onClick={() => void answer(request.sender_id, true)}>
                Accept
              </button>
              <button type="button" className="secondary-button" disabled={busySender !== null} onClick={() => void answer(request.sender_id, false)}>
                Decline
              </button>
            </div>
          </li>
        ))}
      </ul>
      <p className="account-note">You can change your answer later on the My account page.</p>
      {errorMessage && <p className="error" role="alert">{errorMessage}</p>}
    </section>
  )
}

export default MessageRequestsBox
