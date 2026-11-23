import { useEffect, useState } from 'react'
import { answerMessagePermission, fetchMessagePermissions } from './api'
import type { MessagePermission } from './types'

// "Posts sent to you" on My account (2026-11-23): everyone who has asked to send the member posts to them alone,
// with the answer, and Allow or Block to change it. Shown only when there is someone.
function MessagePermissionsSection() {
  const [permissions, setPermissions] = useState<MessagePermission[]>([])
  const [busySender, setBusySender] = useState<number | null>(null)
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    fetchMessagePermissions(controller.signal)
      .then(setPermissions)
      .catch(() => setPermissions([]))
    return () => controller.abort()
  }, [])

  async function answer(senderId: number, accept: boolean) {
    setBusySender(senderId)
    setErrorMessage('')
    try {
      const changed = await answerMessagePermission(senderId, accept)
      setPermissions((all) => all.map((permission) => (permission.sender_id === senderId ? changed : permission)))
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Your answer could not be saved.')
    } finally {
      setBusySender(null)
    }
  }

  if (permissions.length === 0) {
    return null
  }
  const words = { pending: 'Waiting for your answer', accepted: 'Allowed', declined: 'Blocked' }
  return (
    <section className="message-permissions" aria-labelledby="message-permissions-heading">
      <h2 id="message-permissions-heading">Posts sent to you</h2>
      <p className="account-note">
        People who asked to send you posts that only the two of you see. Blocked people cannot send you posts;
        allowing them again shows what they sent.
      </p>
      <table className="message-permissions-table">
        <tbody>
          {permissions.map((permission) => (
            <tr key={permission.sender_id}>
              <td>{permission.sender}</td>
              <td>{words[permission.status]}</td>
              <td>
                <div className="note-actions">
                  {permission.status !== 'accepted' && (
                    <button type="button" className="secondary-button small-button" disabled={busySender !== null} onClick={() => void answer(permission.sender_id, true)}>
                      Allow
                    </button>
                  )}
                  {permission.status !== 'declined' && (
                    <button type="button" className="secondary-button small-button" disabled={busySender !== null} onClick={() => void answer(permission.sender_id, false)}>
                      Block
                    </button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {errorMessage && <p className="error" role="alert">{errorMessage}</p>}
    </section>
  )
}

export default MessagePermissionsSection
