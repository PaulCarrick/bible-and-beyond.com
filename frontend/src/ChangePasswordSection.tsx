import { useState } from 'react'
import type { KeyboardEvent } from 'react'
import { changePassword } from './api'

// "Change your password" on the My account page (added 2026-11-15). A plain container with a type="button"
// Save, not a form, so it can never end up inside another form (see "Notes" in CLAUDE.md). The server checks
// the current password, applies the site's rules to the new one and logs the account out everywhere else.
function ChangePasswordSection() {
  const [currentPassword, setCurrentPassword] = useState('')
  const [password, setPassword] = useState('')
  const [passwordConfirmation, setPasswordConfirmation] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')

  async function save() {
    if (isSaving) {
      return
    }
    setMessage('')
    setErrorMessage('')
    if (!currentPassword || !password) {
      setErrorMessage('Please type your current password and the new one twice.')
      return
    }
    setIsSaving(true)
    try {
      await changePassword(currentPassword, password, passwordConfirmation)
      setCurrentPassword('')
      setPassword('')
      setPasswordConfirmation('')
      setMessage('Your password has been changed. Any other device that was logged in will need the new password.')
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'The password could not be changed.')
    } finally {
      setIsSaving(false)
    }
  }

  function clear() {
    setCurrentPassword('')
    setPassword('')
    setPasswordConfirmation('')
    setMessage('')
    setErrorMessage('')
  }

  function saveOnEnter(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter') {
      event.preventDefault()
      void save()
    }
  }

  return (
    <section className="change-password" aria-labelledby="change-password-heading">
      <h2 id="change-password-heading">Change your password</h2>
      <div className="contact-form">
        <label className="contact-field">
          Current password
          <input
            type="password"
            value={currentPassword}
            maxLength={128}
            autoComplete="current-password"
            onChange={(event) => setCurrentPassword(event.target.value)}
            onKeyDown={saveOnEnter}
          />
        </label>
        <label className="contact-field">
          New password (at least 8 characters)
          <input
            type="password"
            value={password}
            maxLength={128}
            autoComplete="new-password"
            onChange={(event) => setPassword(event.target.value)}
            onKeyDown={saveOnEnter}
          />
        </label>
        <label className="contact-field">
          New password again
          <input
            type="password"
            value={passwordConfirmation}
            maxLength={128}
            autoComplete="new-password"
            onChange={(event) => setPasswordConfirmation(event.target.value)}
            onKeyDown={saveOnEnter}
          />
        </label>
        {errorMessage && (
          <p className="error" role="alert">
            {errorMessage}
          </p>
        )}
        {message && <p role="status">{message}</p>}
        <div className="note-actions">
          <button type="button" className="primary-button" disabled={isSaving} onClick={() => void save()}>
            {isSaving ? 'Saving…' : 'Change password'}
          </button>
          <button type="button" className="secondary-button" disabled={isSaving} onClick={clear}>
            Cancel
          </button>
        </div>
      </div>
    </section>
  )
}

export default ChangePasswordSection
