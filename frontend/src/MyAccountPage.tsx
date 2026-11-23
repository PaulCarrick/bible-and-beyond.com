import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { deleteVerseSubscription, fetchVerseSubscription, savePhone, saveVerseSubscription } from './api'
import ChangePasswordSection from './ChangePasswordSection'
import CloseAccountSection from './CloseAccountSection'
import HeadShotSection from './HeadShotSection'
import { deliveryChoice } from './deliveryChoice'
import TextMessageChoices from './TextMessageChoices'
import { formatUsPhone, nextPhoneValue } from './phoneFormat'
import { ownTimeZone } from './timeZones'
import VerseADayChoice from './VerseADayChoice'
import type { AccountUser } from './types'
import type { View } from './views'

interface MyAccountPageProps {
  user: AccountUser | null
  // False until the site knows whether anyone is logged in.
  isAccountKnown: boolean
  // True once the visitor has closed their account in this visit (the page says so).
  wasAccountClosed: boolean
  onUserChanged: (user: AccountUser) => void
  onNavigate: (view: View) => void
  // After the member closes their account: the site forgets them (this page then says it was closed).
  onAccountClosed: () => void
}

// My account (added 2026-11-15 with text messages, the owner's request): the logged-in member's address, their
// phone number with "This is a cell number", how their messages reach them (Send via Email, Send via SMS; added
// 2026-11-16) and the verse a day, which they can change here, and their picture (HeadShotSection, 2026-11-23).
// Opened from Account settings in the account menu at the top right. Below them, a section of its own changes
// the password (ChangePasswordSection), and at the foot the
// member can close their account (CloseAccountSection, 2026-11-17).
function MyAccountPage({ user, isAccountKnown, wasAccountClosed, onUserChanged, onNavigate, onAccountClosed }: MyAccountPageProps) {
  const [phone, setPhone] = useState(user?.phone ?? '')
  const [phoneIsCell, setPhoneIsCell] = useState(user?.phone_is_cell ?? false)
  const [sendViaEmail, setSendViaEmail] = useState(user?.send_via_email ?? true)
  const [sendViaSms, setSendViaSms] = useState(user?.send_via_sms ?? false)
  const [sendMultimedia, setSendMultimedia] = useState(user?.send_multimedia ?? false)
  // The verse a day: undefined while loading.
  const [verseLoaded, setVerseLoaded] = useState<boolean | undefined>(undefined)
  const [verseADay, setVerseADay] = useState(false)
  const [verseTime, setVerseTime] = useState('07:00')
  const [timeZone, setTimeZone] = useState(ownTimeZone)
  const [isSaving, setIsSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const userId = user?.id ?? null

  useEffect(() => {
    if (userId === null) {
      return
    }
    const controller = new AbortController()
    fetchVerseSubscription(controller.signal)
      .then((found) => {
        setVerseADay(found !== null)
        if (found) {
          setVerseTime(found.send_time)
          setTimeZone(found.timezone)
        }
        setVerseLoaded(found !== null)
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted) {
          setErrorMessage(error.message)
        }
      })
    return () => controller.abort()
  }, [userId])

  if (user === null && !isAccountKnown) {
    return (
      <div className="account-page">
        <h1>My account</h1>
        <p>Loading…</p>
      </div>
    )
  }
  if (user === null && wasAccountClosed) {
    return (
      <div className="account-page">
        <h1>My account</h1>
        <p role="status">
          Your account has been closed and you have been logged out everywhere. We have sent one last email to your
          address to say so; the site will send you nothing more. Thank you for using the site. To have it reopened,
          ask us through the Contact page.
        </p>
        <div className="note-actions">
          <button type="button" className="secondary-button" onClick={() => onNavigate('welcome')}>
            Go to the welcome page
          </button>
        </div>
      </div>
    )
  }
  if (user === null) {
    return (
      <div className="account-page">
        <h1>My account</h1>
        <p>
          Please{' '}
          <button type="button" className="link-button" onClick={() => onNavigate('login')}>
            log in
          </button>{' '}
          first.
        </p>
      </div>
    )
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (isSaving) {
      return
    }
    setIsSaving(true)
    setMessage('')
    setErrorMessage('')
    const hasPhone = phone.trim() !== ''
    try {
      const hasEmail = Boolean(user?.email)
      const choice = deliveryChoice(phone, phoneIsCell, sendViaEmail, sendViaSms, hasEmail)
      const saved = await savePhone(phone, hasPhone && (phoneIsCell || !hasEmail), choice.sendViaEmail, choice.sendViaSms, sendMultimedia)
      if (verseADay) {
        await saveVerseSubscription(verseTime, timeZone)
      } else if (verseLoaded) {
        await deleteVerseSubscription()
      }
      setVerseLoaded(verseADay)
      onUserChanged(saved)
      setPhone(saved.phone)
      setPhoneIsCell(saved.phone_is_cell)
      setSendViaEmail(saved.send_via_email)
      setSendViaSms(saved.send_via_sms)
      setSendMultimedia(saved.send_multimedia)
      setMessage(
        saved.sms_opt_in && !user?.sms_opt_in
          ? 'Saved. Texts are on: we have sent a text to confirm.'
          : 'Saved.',
      )
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'That could not be saved.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="account-page">
      <h1>My account</h1>
      <p>
        Logged in as <strong>{user.email ?? user.phone}</strong>
        {user.first_name || user.last_name ? ` (${[user.first_name, user.last_name].filter(Boolean).join(' ')})` : ''}.
      </p>
      {!user.email && (
        <p className="account-note">
          Your account has no email address: you log in with your phone number, and nothing is sent to you by email.
          {user.logs_in_with_phone && !user.phone_verified && ' Type the code we texted you (at the top of the page) to confirm your number.'}
        </p>
      )}
      {user.sms_stopped && !user.sms_opt_in && (
        <p className="account-note">
          You replied STOP to one of our texts, so texts are off and your messages come by email for now. Save
          with <em>Send via SMS</em> ticked below to turn texts back on (you may also need to reply START to our
          number).
        </p>
      )}
      <HeadShotSection user={user} onUserChanged={onUserChanged} />
      <form className="contact-form" onSubmit={handleSubmit}>
        <label className="contact-field">
          {user.email ? 'Phone (optional)' : 'Cell phone number (you log in with it)'}
          <input
            type="tel"
            value={phone}
            maxLength={40}
            autoComplete="tel"
            placeholder="+1 (555) 123-4567"
            required={!user.email}
            onChange={(event) => setPhone(nextPhoneValue(phone, event.target.value))}
            onBlur={() => setPhone(formatUsPhone(phone))}
          />
        </label>
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
          hasEmail={Boolean(user.email)}
        />
        {verseLoaded !== undefined && (
          <VerseADayChoice
            isOn={verseADay}
            sendTime={verseTime}
            timeZone={timeZone}
            onIsOnChange={setVerseADay}
            onSendTimeChange={setVerseTime}
            onTimeZoneChange={setTimeZone}
          />
        )}
        {user.email && !user.email_verified && (sendViaSms || verseADay) && (
          <p className="account-note">
            Texts and the verse a day start once you have confirmed your email address, as the other emails do.
          </p>
        )}
        {!user.email && !user.phone_verified && (sendViaSms || verseADay) && (
          <p className="account-note">Texts and the verse a day start once you have confirmed your phone number.</p>
        )}
        {user.logs_in_with_phone && phone !== user.phone && (
          <p className="account-note">A new number is the one you log in with; we will text it a code to confirm it.</p>
        )}
        {errorMessage && (
          <p className="error" role="alert">
            {errorMessage}
          </p>
        )}
        {message && <p role="status">{message}</p>}
        <div className="note-actions">
          <button type="submit" className="primary-button" disabled={isSaving}>
            {isSaving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </form>
      <ChangePasswordSection />
      <CloseAccountSection onClosed={onAccountClosed} />
    </div>
  )
}

export default MyAccountPage
