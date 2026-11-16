import { useMemo } from 'react'
import { allTimeZones } from './timeZones'

interface VerseADayChoiceProps {
  isOn: boolean
  sendTime: string
  timeZone: string
  onIsOnChange: (value: boolean) => void
  onSendTimeChange: (value: string) => void
  onTimeZoneChange: (value: string) => void
}

// "Send me a verse a day" (the sign-up form and the My account page; the owner's request, 2026-11-15), with its
// time of day and time zone once ticked. The verse comes by email, text or both, as the member chose under "How
// should we send you messages?" (verse_a_day.py, sms.deliver).
function VerseADayChoice({ isOn, sendTime, timeZone, onIsOnChange, onSendTimeChange, onTimeZoneChange }: VerseADayChoiceProps) {
  const zones = useMemo(() => allTimeZones(), [])
  return (
    <div className="prayer-options verse-a-day-choice">
      <label className="inline-label">
        <input type="checkbox" checked={isOn} onChange={(event) => onIsOnChange(event.target.checked)} />
        Send me a verse a day
        <small>
          A Bible verse chosen at random from well-known passages, each day by email, text or both (as you chose
          above), with a link to read it in context.
        </small>
      </label>
      {isOn && (
        <div className="verse-a-day-time">
          <label className="contact-field">
            Time of day
            <input type="time" value={sendTime} step={300} onChange={(event) => onSendTimeChange(event.target.value)} />
          </label>
          <label className="contact-field">
            Time zone
            <select value={timeZone} onChange={(event) => onTimeZoneChange(event.target.value)}>
              {zones.map((zone) => (
                <option key={zone} value={zone}>
                  {zone.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
    </div>
  )
}

export default VerseADayChoice
