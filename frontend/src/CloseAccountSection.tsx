import { useState } from 'react'
import type { KeyboardEvent } from 'react'
import { closeAccount } from './api'

interface CloseAccountSectionProps {
  // Called once the account is closed (the site forgets the member; My account says it was closed).
  onClosed: () => void
}

// "Close your account" at the foot of the My account page (added 2026-11-17 at the owner's request; first a
// delete, then a close: nothing is deleted). A button opens a box that says what closing does and asks for the
// password; Close my account closes it (POST /account/close), Cancel closes the box. A plain container with
// type="button" buttons, not a form, like ChangePasswordSection. The server checks the password, marks the account
// closed, logs out every device and sends one goodbye email; after that it cannot log in and gets no emails or texts.
function CloseAccountSection({ onClosed }: CloseAccountSectionProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [isClosing, setIsClosing] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')

  async function close() {
    if (isClosing) {
      return
    }
    setErrorMessage('')
    if (!password) {
      setErrorMessage('Please type your password to close your account.')
      return
    }
    setIsClosing(true)
    try {
      await closeAccount(password)
      onClosed()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Your account could not be closed.')
      setIsClosing(false)
    }
  }

  function cancel() {
    setIsOpen(false)
    setPassword('')
    setErrorMessage('')
  }

  function closeOnEnter(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter') {
      event.preventDefault()
      void close()
    }
  }

  return (
    <section className="close-account" aria-labelledby="close-account-heading">
      <h2 id="close-account-heading">Close your account</h2>
      {!isOpen ? (
        <>
          <p>Closing your account stops it: you can no longer log in, and the site sends you no more emails or texts.</p>
          <div className="note-actions">
            <button type="button" className="danger-button" onClick={() => setIsOpen(true)}>
              Close my account…
            </button>
          </div>
        </>
      ) : (
        <div className="contact-form">
          <p>
            Once your account is closed you can no longer log in, and the site sends you no more emails or texts (no
            devotionals, verse a day, prayer list, replies or group messages). We send one last email to say it was
            closed. You will be logged out on every device. What you wrote stays as it is. To have your account reopened,
            or deleted with everything in it, ask us through the Contact page.
          </p>
          <label className="contact-field">
            Type your password to confirm
            <input
              type="password"
              value={password}
              maxLength={128}
              autoComplete="current-password"
              onChange={(event) => setPassword(event.target.value)}
              onKeyDown={closeOnEnter}
              autoFocus
            />
          </label>
          {errorMessage && (
            <p className="error" role="alert">
              {errorMessage}
            </p>
          )}
          <div className="note-actions">
            <button type="button" className="danger-button" disabled={isClosing} onClick={() => void close()}>
              {isClosing ? 'Closing…' : 'Close my account'}
            </button>
            <button type="button" className="secondary-button" disabled={isClosing} onClick={cancel}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  )
}

export default CloseAccountSection
