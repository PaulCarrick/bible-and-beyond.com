import { useState } from 'react'
import type { FormEvent } from 'react'
import { logIn, registerAccount } from './api'
import type { AccountUser } from './types'

interface AccountPageProps {
  // "register" is Setup Account (an email and the password twice); "login" asks for the email and password.
  mode: 'register' | 'login'
  onDone: (user: AccountUser) => void
  onSwitchMode: () => void
}

// The page for setting up an account and the page for logging in. Neither is required to use the site.
function AccountPage({ mode, onDone, onSwitchMode }: AccountPageProps) {
  const [emailAddress, setEmailAddress] = useState('')
  const [password, setPassword] = useState('')
  const [passwordConfirmation, setPasswordConfirmation] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [isSending, setIsSending] = useState(false)
  const isRegistering = mode === 'register'

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (isSending) {
      return
    }
    setErrorMessage('')
    if (isRegistering && password !== passwordConfirmation) {
      setErrorMessage('The two passwords are not the same.')
      return
    }
    setIsSending(true)
    try {
      const user = isRegistering
        ? await registerAccount(emailAddress, password, passwordConfirmation)
        : await logIn(emailAddress, password)
      if (user) {
        onDone(user)
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Something went wrong. Please try again.')
    } finally {
      setIsSending(false)
    }
  }

  return (
    <div className="account-page">
      <h1>{isRegistering ? 'Set up account' : 'Log in'}</h1>
      <p>
        {isRegistering
          ? 'An account is optional. Everything on this site works without one; it will be used later for features that are just for you.'
          : 'Logging in is optional. Everything on this site works without it.'}
      </p>

      <form className="contact-form" onSubmit={handleSubmit}>
        <label className="contact-field">
          Email Address
          <input
            type="email"
            value={emailAddress}
            maxLength={254}
            required
            autoComplete="email"
            onChange={(event) => setEmailAddress(event.target.value)}
          />
        </label>
        <label className="contact-field">
          Password
          <input
            type="password"
            value={password}
            minLength={isRegistering ? 10 : undefined}
            maxLength={128}
            required
            autoComplete={isRegistering ? 'new-password' : 'current-password'}
            onChange={(event) => setPassword(event.target.value)}
          />
          {isRegistering && <small>At least 10 characters.</small>}
        </label>
        {isRegistering && (
          <label className="contact-field">
            Password again
            <input
              type="password"
              value={passwordConfirmation}
              maxLength={128}
              required
              autoComplete="new-password"
              onChange={(event) => setPasswordConfirmation(event.target.value)}
            />
          </label>
        )}

        {errorMessage && (
          <p className="error" role="alert">
            {errorMessage}
          </p>
        )}

        <button type="submit" className="primary-button" disabled={isSending}>
          {isSending ? 'Please wait…' : isRegistering ? 'Set up account' : 'Log in'}
        </button>
      </form>

      <p>
        {isRegistering ? 'Already have an account? ' : 'No account yet? '}
        <button type="button" className="link-button" onClick={onSwitchMode}>
          {isRegistering ? 'Log in' : 'Set up account'}
        </button>
      </p>
    </div>
  )
}

export default AccountPage
