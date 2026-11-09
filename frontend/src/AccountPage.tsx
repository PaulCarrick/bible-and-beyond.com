import { useState } from 'react'
import type { FormEvent } from 'react'
import { forgotPassword, logIn, registerAccount, resetPassword } from './api'
import type { AccountUser } from './types'
import type { View } from './views'

interface AccountPageProps {
  // register: Set up account (email and the password twice, which are required; first name, last name and phone,
  // which are optional).
  // login: email and password.
  // forgot: ask for a reset link. reset: choose a new password with the link's token.
  mode: 'register' | 'login' | 'forgot' | 'reset'
  token: string
  onDone: (user: AccountUser) => void
  onNavigate: (view: View) => void
}

// The pages for setting up an account, logging in and getting a forgotten password back. None is
// needed to use the site.
function AccountPage({ mode, token, onDone, onNavigate }: AccountPageProps) {
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [phone, setPhone] = useState('')
  const [emailAddress, setEmailAddress] = useState('')
  const [password, setPassword] = useState('')
  const [passwordConfirmation, setPasswordConfirmation] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [doneMessage, setDoneMessage] = useState('')
  const [isSending, setIsSending] = useState(false)
  const needsTwoPasswords = mode === 'register' || mode === 'reset'

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (isSending) {
      return
    }
    setErrorMessage('')
    if (needsTwoPasswords && password !== passwordConfirmation) {
      setErrorMessage('The two passwords are not the same.')
      return
    }
    setIsSending(true)
    try {
      if (mode === 'forgot') {
        await forgotPassword(emailAddress)
        setDoneMessage(
          'If an account has that email address, a link to choose a new password is on its way. It works for an hour.',
        )
      } else if (mode === 'reset') {
        await resetPassword(token, password, passwordConfirmation)
        setDoneMessage('Your password has been changed. You can log in with it now.')
      } else {
        const user =
          mode === 'register'
            ? await registerAccount({ email: emailAddress, password, passwordConfirmation, firstName, lastName, phone })
            : await logIn(emailAddress, password)
        if (user) {
          onDone(user)
        }
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Something went wrong. Please try again.')
    } finally {
      setIsSending(false)
    }
  }

  const heading = { register: 'Set up account', login: 'Log in', forgot: 'Forgot your password?', reset: 'Choose a new password' }[mode]
  const intro = {
    register:
      'An account is optional. Everything on this site works without one; it will be used later for features that are just for you. We will email you a link to confirm your address.',
    login: 'Logging in is optional. Everything on this site works without it.',
    forgot: 'Enter the email address of your account and we will email you a link to choose a new password.',
    reset: 'Choose a new password for your account.',
  }[mode]
  const submitLabel = { register: 'Set up account', login: 'Log in', forgot: 'Send the link', reset: 'Change password' }[mode]

  return (
    <div className="account-page">
      <h1>{heading}</h1>
      <p>{intro}</p>

      {doneMessage ? (
        <p className="contact-sent" role="status">
          {doneMessage}{' '}
          {mode === 'reset' && (
            <button type="button" className="link-button" onClick={() => onNavigate('login')}>
              Log in
            </button>
          )}
        </p>
      ) : (
        <form className="contact-form" onSubmit={handleSubmit}>
          {mode === 'register' && (
            <>
              <label className="contact-field">
                First name (optional)
                <input
                  type="text"
                  value={firstName}
                  maxLength={100}
                  autoComplete="given-name"
                  onChange={(event) => setFirstName(event.target.value)}
                />
              </label>
              <label className="contact-field">
                Last name (optional)
                <input
                  type="text"
                  value={lastName}
                  maxLength={100}
                  autoComplete="family-name"
                  onChange={(event) => setLastName(event.target.value)}
                />
              </label>
            </>
          )}
          {mode !== 'reset' && (
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
          )}
          {mode === 'register' && (
            <label className="contact-field">
              Phone (optional)
              <input
                type="tel"
                value={phone}
                maxLength={40}
                autoComplete="tel"
                onChange={(event) => setPhone(event.target.value)}
              />
            </label>
          )}
          {mode !== 'forgot' && (
            <label className="contact-field">
              {mode === 'reset' ? 'New password' : 'Password'}
              <input
                type="password"
                value={password}
                minLength={needsTwoPasswords ? 10 : undefined}
                maxLength={128}
                required
                autoComplete={needsTwoPasswords ? 'new-password' : 'current-password'}
                onChange={(event) => setPassword(event.target.value)}
              />
              {needsTwoPasswords && <small>At least 10 characters.</small>}
            </label>
          )}
          {needsTwoPasswords && (
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
            {isSending ? 'Please wait…' : submitLabel}
          </button>
        </form>
      )}

      {mode === 'login' && (
        <p>
          <button type="button" className="link-button" onClick={() => onNavigate('forgot')}>
            Forgot your password?
          </button>
        </p>
      )}
      {(mode === 'register' || mode === 'login') && (
        <p>
          {mode === 'register' ? 'Already have an account? ' : 'No account yet? '}
          <button type="button" className="link-button" onClick={() => onNavigate(mode === 'register' ? 'login' : 'register')}>
            {mode === 'register' ? 'Log in' : 'Set up account'}
          </button>
        </p>
      )}
      {mode === 'forgot' && (
        <p>
          <button type="button" className="link-button" onClick={() => onNavigate('login')}>
            Back to log in
          </button>
        </p>
      )}
    </div>
  )
}

export default AccountPage
