import { useEffect, useState } from 'react'
import { answerMessageRequestByLink, fetchMessageRequestByLink } from './api'
import type { MessagePermission } from './types'
import type { View } from './views'

interface MessageRequestPageProps {
  token: string
  onNavigate: (view: View) => void
}

// The page the link in a request email or text opens (2026-11-23): someone would like to send the member posts
// that only the two of them see. Accept or Decline, without logging in (the link is the member's own).
function MessageRequestPage({ token, onNavigate }: MessageRequestPageProps) {
  const [request, setRequest] = useState<(MessagePermission & { recipient_first_name: string }) | null>(null)
  const [message, setMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [isBusy, setIsBusy] = useState(false)

  useEffect(() => {
    let isCurrent = true
    fetchMessageRequestByLink(token)
      .then((found) => isCurrent && setRequest(found))
      .catch((error: Error) => isCurrent && setErrorMessage(error.message))
    return () => {
      isCurrent = false
    }
  }, [token])

  async function answer(accept: boolean) {
    setIsBusy(true)
    setErrorMessage('')
    try {
      const saved = await answerMessageRequestByLink(token, accept)
      setRequest((shown) => (shown ? { ...shown, status: saved.status } : shown))
      setMessage(
        accept
          ? `Done. ${saved.sender}’s posts to you now show on the Conversations page, and you will not be asked again.`
          : `Done. ${saved.sender} cannot send you posts. You can change this on your My account page.`,
      )
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Your answer could not be saved.')
    } finally {
      setIsBusy(false)
    }
  }

  return (
    <div className="account-page">
      <h1>Posts from another member</h1>
      {request === null && !errorMessage && <p>Loading…</p>}
      {request && !message && (
        <>
          <p>
            {request.recipient_first_name ? `${request.recipient_first_name}, ` : ''}
            <strong>{request.sender}</strong> would like to send you posts in Conversations that only the two of you
            see. Nothing they wrote shows until you accept.
          </p>
          {request.status !== 'pending' && (
            <p className="account-note">
              You already {request.status === 'accepted' ? 'accepted' : 'declined'} posts from them. You can change it
              here.
            </p>
          )}
          <p>If you accept, you will not be asked again about them. If you decline, they cannot send you posts.</p>
          <div className="note-actions">
            <button type="button" className="primary-button" disabled={isBusy} onClick={() => void answer(true)}>
              Accept
            </button>
            <button type="button" className="secondary-button" disabled={isBusy} onClick={() => void answer(false)}>
              Decline
            </button>
          </div>
        </>
      )}
      {message && (
        <>
          <p role="status">{message}</p>
          <div className="note-actions">
            <button type="button" className="secondary-button" onClick={() => onNavigate('conversations')}>
              Open Conversations
            </button>
          </div>
        </>
      )}
      {errorMessage && <p className="error" role="alert">{errorMessage}</p>}
    </div>
  )
}

export default MessageRequestPage
