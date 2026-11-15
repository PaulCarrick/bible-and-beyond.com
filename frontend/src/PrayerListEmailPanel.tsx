import { useContext, useEffect, useMemo, useState } from 'react'
import { AccountContext } from './AccountContext'
import { deletePrayerListSubscription, fetchPrayerListSubscription, savePrayerListSubscription } from './api'
import { allTimeZones, ownTimeZone } from './timeZones'
import type { PrayerListSubscription } from './types'

// The days as the server numbers them (0 Monday, like Python's weekday()).
const weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

// "Email me the prayer list each week", at the top of the Prayer Wall: a day, a time and a time zone; change them or
// stop. Each email holds the past week's requests that their authors chose to email (not answered or private ones),
// and none is sent in a week with no new ones (prayer_list.py). Any logged-in visitor with a confirmed address may
// sign up: no invitation needed.
function PrayerListEmailPanel() {
  const { user, onNavigate } = useContext(AccountContext)
  const userId = user?.id ?? null
  // undefined while loading, null when the visitor does not get it.
  const [subscription, setSubscription] = useState<PrayerListSubscription | null | undefined>(undefined)
  const [sendWeekday, setSendWeekday] = useState(6)
  const [sendTime, setSendTime] = useState('07:00')
  const [timeZone, setTimeZone] = useState(ownTimeZone)
  const [isChanging, setIsChanging] = useState(false)
  const [isBusy, setIsBusy] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [message, setMessage] = useState('')
  const zones = useMemo(() => allTimeZones(), [])

  useEffect(() => {
    if (userId === null) {
      return
    }
    const controller = new AbortController()
    fetchPrayerListSubscription(controller.signal)
      .then((found) => {
        setSubscription(found)
        if (found) {
          setSendWeekday(found.send_weekday)
          setSendTime(found.send_time)
          setTimeZone(found.timezone)
        }
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted) {
          setErrorMessage(error.message)
        }
      })
    return () => controller.abort()
  }, [userId])

  async function handleSave() {
    if (isBusy) {
      return
    }
    setIsBusy(true)
    setErrorMessage('')
    setMessage('')
    try {
      setSubscription(await savePrayerListSubscription(sendWeekday, sendTime, timeZone))
      setIsChanging(false)
      setMessage('Saved.')
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'That could not be saved.')
    } finally {
      setIsBusy(false)
    }
  }

  async function handleStop() {
    if (isBusy) {
      return
    }
    setIsBusy(true)
    setErrorMessage('')
    setMessage('')
    try {
      await deletePrayerListSubscription()
      setSubscription(null)
      setIsChanging(false)
      setMessage('The emails are stopped.')
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'That could not be stopped.')
    } finally {
      setIsBusy(false)
    }
  }

  const summary =
    subscription === undefined || subscription === null
      ? 'Email me the prayer list each week'
      : `The prayer list is emailed to you every ${weekdays[subscription.send_weekday]} at ${subscription.send_time}`
  const showForm = subscription === null || isChanging

  return (
    <details className="email-panel prayer-list-panel">
      <summary>{summary}</summary>

      {user === null ? (
        <p>
          <button type="button" className="link-button" onClick={() => onNavigate('login')}>
            Log in
          </button>{' '}
          or{' '}
          <button type="button" className="link-button" onClick={() => onNavigate('register')}>
            set up an account
          </button>{' '}
          to get the prayer list by email each week.
        </p>
      ) : !user.email_verified ? (
        <p>
          Please confirm your email address first: we sent a link to {user.email}. Use the reminder at the top of the
          page if you need it again.
        </p>
      ) : subscription === undefined && !errorMessage ? (
        <p>Loading…</p>
      ) : (
        <div className="email-panel-body">
          {subscription && !isChanging && (
            <p>
              The prayer list is emailed to {user.email} every {weekdays[subscription.send_weekday]} at{' '}
              {subscription.send_time} ({subscription.timezone}), when there are new requests.
            </p>
          )}

          {showForm && (
            <div className="contact-form">
              <p>
                Once a week, the prayer requests that members chose to email in the past week are sent to {user.email}.
                Nothing is sent in a week with no new requests. Answered requests are left out, and private ones go only to
                the site&rsquo;s administrators.
              </p>
              <label className="contact-field">
                Day of the week
                <select value={sendWeekday} onChange={(event) => setSendWeekday(Number(event.target.value))}>
                  {weekdays.map((name, number) => (
                    <option key={name} value={number}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="contact-field">
                Time of day
                <input type="time" value={sendTime} step={300} onChange={(event) => setSendTime(event.target.value)} />
              </label>
              <label className="contact-field">
                Time zone
                <select value={timeZone} onChange={(event) => setTimeZone(event.target.value)}>
                  {zones.map((zone) => (
                    <option key={zone} value={zone}>
                      {zone.replace(/_/g, ' ')}
                    </option>
                  ))}
                </select>
              </label>
              <small>It is sent within five minutes of that time, starting the next time that day comes round.</small>
              <div className="note-actions">
                <button type="button" className="primary-button" disabled={isBusy || sendTime === ''} onClick={handleSave}>
                  {isBusy ? 'Saving…' : subscription ? 'Save the change' : 'Email it to me each week'}
                </button>
                {subscription && (
                  <button type="button" className="secondary-button" disabled={isBusy} onClick={() => setIsChanging(false)}>
                    Cancel
                  </button>
                )}
              </div>
            </div>
          )}

          {subscription && !isChanging && (
            <div className="note-actions">
              <button type="button" className="link-button" onClick={() => setIsChanging(true)}>
                Change the day or time
              </button>
              <button type="button" className="link-button danger" disabled={isBusy} onClick={handleStop}>
                Stop the emails
              </button>
            </div>
          )}
        </div>
      )}

      {message && <p role="status">{message}</p>}
      {errorMessage && (
        <p className="error" role="alert">
          {errorMessage}
        </p>
      )}
    </details>
  )
}

export default PrayerListEmailPanel
