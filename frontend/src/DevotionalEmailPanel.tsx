import { useContext, useEffect, useMemo, useState } from 'react'
import { AccountContext } from './AccountContext'
import { deleteSubscription, fetchSubscriptions, saveSubscription } from './api'
import type { DevotionalContents, DevotionalInfo, DevotionalSubscription } from './types'

interface DevotionalEmailPanelProps {
  devotional: DevotionalInfo
  // Where the reader is now: a devotional with chapters offers to start with this chapter.
  sections: DevotionalContents['sections']
  currentSection: number
  currentUnit: number
}

function allTimeZones(): string[] {
  const own = Intl.DateTimeFormat().resolvedOptions().timeZone
  const names = new Set<string>(Intl.supportedValuesOf('timeZone'))
  names.add('UTC')
  if (own) {
    names.add(own)
  }
  return [...names].sort()
}

// "Email me this devotional each day": choose a time and a time zone (and, for a devotional with chapters,
// the chapter to start with); change them or stop. Emails go to the address of the logged-in account.
function DevotionalEmailPanel({ devotional, sections, currentSection, currentUnit }: DevotionalEmailPanelProps) {
  const { user, onNavigate } = useContext(AccountContext)
  const userId = user?.id ?? null
  const [subscription, setSubscription] = useState<DevotionalSubscription | null | undefined>(undefined)
  const [sendTime, setSendTime] = useState('07:00')
  const [timeZone, setTimeZone] = useState(() => Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC')
  const [start, setStart] = useState('')
  const [isChanging, setIsChanging] = useState(false)
  const [isBusy, setIsBusy] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [message, setMessage] = useState('')
  const zones = useMemo(() => allTimeZones(), [])
  const isChapters = devotional.kind === 'chapters'

  // Whether this visitor already gets this devotional.
  useEffect(() => {
    if (userId === null) {
      return
    }
    const controller = new AbortController()
    fetchSubscriptions(controller.signal)
      .then((all) => {
        const found = all.find((entry) => entry.devotional_id === devotional.id) ?? null
        setSubscription(found)
        if (found) {
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
  }, [userId, devotional.id])

  async function handleSave() {
    if (isBusy) {
      return
    }
    setIsBusy(true)
    setErrorMessage('')
    setMessage('')
    try {
      // "section:unit" of the chapter chosen; the one on screen unless the visitor chose another.
      const [startSection, startUnit] = (start || `${currentSection}:${currentUnit}`).split(':').map(Number)
      setSubscription(
        await saveSubscription(devotional.id, {
          sendTime,
          timezone: timeZone,
          ...(isChapters && (subscription === null || start !== '') ? { startSection, startUnit } : {}),
        }),
      )
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
      await deleteSubscription(devotional.id)
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
      ? 'Email me this devotional each day'
      : `Emailed to you each day at ${subscription.send_time}`
  const showForm = subscription === null || isChanging

  return (
    <details className="email-panel">
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
          to get {devotional.name} by email each day.
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
              You get {devotional.name} at {user.email} every day at {subscription.send_time} ({subscription.timezone}).
              {isChapters && subscription.next_title && <> The next one is {subscription.next_title}.</>}
            </p>
          )}

          {showForm && (
            <div className="contact-form">
              <p>
                {isChapters
                  ? `One chapter of ${devotional.name} will be emailed to ${user.email} each day, in order, until the last.`
                  : `The day's reading of ${devotional.name} will be emailed to ${user.email}.`}
              </p>
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
              {isChapters && (
                <label className="contact-field">
                  {subscription ? 'Start again from' : 'Start with'}
                  <select value={start || `${currentSection}:${currentUnit}`} onChange={(event) => setStart(event.target.value)}>
                    {sections.map((section) => (
                      <optgroup key={section.number} label={section.title}>
                        {section.units.map((unit) => (
                          <option key={unit.number} value={`${section.number}:${unit.number}`}>
                            {unit.title}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </label>
              )}
              <small>
                It is sent within five minutes of that time. Today&rsquo;s is skipped if the time has already passed.
              </small>
              <div className="note-actions">
                <button type="button" className="primary-button" disabled={isBusy || sendTime === ''} onClick={handleSave}>
                  {isBusy ? 'Saving…' : subscription ? 'Save the change' : 'Email it to me each day'}
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
                Change the time{isChapters ? ' or chapter' : ''}
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

export default DevotionalEmailPanel
