import { useState } from 'react'
import type { FormEvent } from 'react'
import { confirmPhone, resendPhoneCode } from './api'
import type { AccountUser } from './types'

interface ConfirmPhoneBoxProps {
  user: AccountUser
  onConfirmed: (user: AccountUser) => void
}

// For an account that logs in with its phone and has not confirmed it yet (2026-11-17, the owner's request): the
// 6-digit code texted to the number, Confirm, and "Text me a new code". Shown at the top of every page, like the
// reminder to confirm an email address. Until it is confirmed the account works (notes, lists, the Prayer Wall)
// but gets no texts. The server counts wrong codes and refuses after five.
function ConfirmPhoneBox({ user, onConfirmed }: ConfirmPhoneBoxProps) {
  const [code, setCode] = useState('')
  const [message, setMessage] = useState('')
  const [isError, setIsError] = useState(false)
  const [isSending, setIsSending] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (isSending) {
      return
    }
    setIsSending(true)
    setMessage('')
    try {
      const confirmed = await confirmPhone(code)
      if (confirmed) {
        onConfirmed(confirmed)
      }
    } catch (error) {
      setIsError(true)
      setMessage(error instanceof Error ? error.message : 'That code could not be checked.')
    } finally {
      setIsSending(false)
    }
  }

  function sendAnother() {
    setMessage('')
    resendPhoneCode()
      .then(() => {
        setIsError(false)
        setMessage('A new code is on its way. It works for 15 minutes.')
      })
      .catch((error: Error) => {
        setIsError(true)
        setMessage(error.message)
      })
  }

  return (
    <form className="contact-sent confirm-phone" onSubmit={handleSubmit}>
      <label className="inline-label">
        Please confirm your phone number: type the code we texted to {user.phone}
        <input
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={8}
          size={8}
          value={code}
          onChange={(event) => setCode(event.target.value)}
        />
      </label>{' '}
      <button type="submit" className="link-button" disabled={isSending || code.trim() === ''}>
        Confirm
      </button>{' '}
      <button type="button" className="link-button" onClick={sendAnother}>
        Text me a new code
      </button>
      {message && (
        <span className={isError ? 'error' : undefined} role="status">
          {' '}
          {message}
        </span>
      )}
    </form>
  )
}

export default ConfirmPhoneBox
