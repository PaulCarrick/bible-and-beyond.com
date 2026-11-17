import { useState } from 'react'
import type { FormEvent } from 'react'
import { forgotPassword, logIn, registerAccount, resetPassword } from './api'
import { deliveryChoice } from './deliveryChoice'
import TextMessageChoices from './TextMessageChoices'
import { formatUsPhone, nextPhoneValue } from './phoneFormat'
import { ownTimeZone } from './timeZones'
import VerseADayChoice from './VerseADayChoice'
import type { AccountUser } from './types'
import type { View } from './views'

interface AccountPageProps {
  // register: Set up account (an email address or a cell phone number, and the password twice; first name, last
  // name and, with an email address, the phone are optional). Without an email address the account logs in with
  // its phone (2026-11-17), confirmed by a texted code.
  // login: email address or phone number, and password.
  // forgot: ask for a reset link (emailed, or texted to a phone that logs in). reset: choose a new password with
  // the link's token.
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
  const [phoneIsCell, setPhoneIsCell] = useState(false)
  const [sendViaEmail, setSendViaEmail] = useState(true)
  const [sendViaSms, setSendViaSms] = useState(false)
  const [sendMultimedia, setSendMultimedia] = useState(false)
  const [verseADay, setVerseADay] = useState(false)
  const [verseTime, setVerseTime] = useState('07:00')
  const [timeZone, setTimeZone] = useState(ownTimeZone)
  const [emailAddress, setEmailAddress] = useState('')
  const [password, setPassword] = useState('')
  const [passwordConfirmation, setPasswordConfirmation] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [doneMessage, setDoneMessage] = useState('')
  const [isSending, setIsSending] = useState(false)
  const needsTwoPasswords = mode === 'register' || mode === 'reset'
  // Sign-up without an email address: the phone is the login, a cell number, and nothing is emailed.
  const hasEmail = emailAddress.trim() !== ''

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
    if (mode === 'register' && !hasEmail && phone.trim() === '') {
      setErrorMessage('Please give an email address or a cell phone number (you can give both).')
      return
    }
    setIsSending(true)
    try {
      if (mode === 'forgot') {
        await forgotPassword(emailAddress)
        setDoneMessage(
          'If an account has that email address or phone number, a link to choose a new password is on its way, by email or by text. It works for an hour.',
        )
      } else if (mode === 'reset') {
        await resetPassword(token, password, passwordConfirmation)
        setDoneMessage('Your password has been changed. You can log in with it now.')
      } else {
        const user =
          mode === 'register'
            ? await registerAccount({
                email: emailAddress,
                password,
                passwordConfirmation,
                firstName,
                lastName,
                phone,
                phoneIsCell: phone.trim() !== '' && (phoneIsCell || !hasEmail),
                ...deliveryChoice(phone, phoneIsCell, sendViaEmail, sendViaSms, hasEmail),
                sendMultimedia,
                verseADay,
                verseTime,
                timezone: timeZone,
              })
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
      'An account is optional. Everything on this site works without one; it will be used later for features that are just for you. Set it up with an email address (we email you a link to confirm it) or, if you have none, with a cell phone number (we text you a code to confirm it, and you log in with it).',
    login: 'Logging in is optional. Everything on this site works without it.',
    forgot: 'Enter the email address of your account, or the phone number you log in with, and we will send you a link to choose a new password (by email or by text).',
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
          {mode === 'register' && (
            <label className="contact-field">
              Email Address
              <input
                type="email"
                value={emailAddress}
                maxLength={254}
                autoComplete="email"
                onChange={(event) => setEmailAddress(event.target.value)}
              />
              <small>Or leave it empty and give a cell phone number below: you then log in with that number.</small>
            </label>
          )}
          {(mode === 'login' || mode === 'forgot') && (
            <label className="contact-field">
              Email address or phone number
              <input
                type="text"
                value={emailAddress}
                maxLength={254}
                required
                autoComplete="username"
                onChange={(event) => setEmailAddress(event.target.value)}
              />
            </label>
          )}
          {mode === 'register' && (
            <label className="contact-field">
              {hasEmail ? 'Phone (optional)' : 'Cell phone number (you log in with it)'}
              <input
                type="tel"
                value={phone}
                maxLength={40}
                autoComplete="tel"
                placeholder="+1 (555) 123-4567"
                required={!hasEmail}
                onChange={(event) => setPhone(nextPhoneValue(phone, event.target.value))}
                onBlur={() => setPhone(formatUsPhone(phone))}
              />
            </label>
          )}
          {mode === 'register' && (
            <TextMessageChoices
              phone={phone}
              phoneIsCell={phoneIsCell}
              sendViaEmail={sendViaEmail}
              sendViaSms={sendViaSms}
              sendMultimedia={sendMultimedia}
              onPhoneIsCellChange={setPhoneIsCell}
              onSendViaEmailChange={setSendViaEmail}
              onSendViaSmsChange={setSendViaSms}
              onSendMultimediaChange={setSendMultimedia}
              hasEmail={hasEmail}
            />
          )}
          {mode === 'register' && (
            <VerseADayChoice
              isOn={verseADay}
              sendTime={verseTime}
              timeZone={timeZone}
              onIsOnChange={setVerseADay}
              onSendTimeChange={setVerseTime}
              onTimeZoneChange={setTimeZone}
            />
          )}
          {mode !== 'forgot' && (
            <label className="contact-field">
              {mode === 'reset' ? 'New password' : 'Password'}
              <input
                type="password"
                value={password}
                minLength={needsTwoPasswords ? 8 : undefined}
                maxLength={128}
                required
                autoComplete={needsTwoPasswords ? 'new-password' : 'current-password'}
                onChange={(event) => setPassword(event.target.value)}
              />
              {needsTwoPasswords && <small>At least 8 characters.</small>}
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

      {/* The other account pages, as buttons under the form (the site's rule: no links beside buttons). */}
      {(mode === 'login' || mode === 'register' || mode === 'forgot') && (
        <div className="account-other-actions">
          {mode === 'login' && (
            <>
              <button type="button" className="secondary-button" onClick={() => onNavigate('forgot')}>
                Forgot your password?
              </button>
              <button type="button" className="secondary-button" onClick={() => onNavigate('register')}>
                No account yet? Set one up
              </button>
            </>
          )}
          {mode === 'register' && (
            <button type="button" className="secondary-button" onClick={() => onNavigate('login')}>
              Already have an account? Log in
            </button>
          )}
          {mode === 'forgot' && (
            <button type="button" className="secondary-button" onClick={() => onNavigate('login')}>
              Back to log in
            </button>
          )}
        </div>
      )}
    </div>
  )
}

export default AccountPage
