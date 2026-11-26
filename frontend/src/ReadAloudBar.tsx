import type { ReadAloudStatus, ReadingPlace } from './useReadAloud'

interface ReadAloudBarProps {
  status: ReadAloudStatus
  place: ReadingPlace | null
  problem: string
  // The browser's voices for the Bible's language (all of them when none match).
  voices: SpeechSynthesisVoice[]
  voiceName: string
  rate: number
  onPause: () => void
  onResume: () => void
  onStop: () => void
  onVoice: (name: string) => void
  onRate: (rate: number) => void
  onShowVerse: () => void
}

const RATES = [0.75, 0.9, 1, 1.15, 1.3]

// The read-aloud player (useReadAloud.ts): at the foot of the screen while the Bible reader reads aloud, with the verse
// being read, Pause or Resume, Stop, the voice and the speed.
function ReadAloudBar({ status, place, problem, voices, voiceName, rate, onPause, onResume, onStop, onVoice, onRate, onShowVerse }: ReadAloudBarProps) {
  if (status === 'idle' && !problem) {
    return null
  }
  return (
    <div className="read-aloud-bar" role="region" aria-label="Read aloud">
      {problem ? (
        <span className="read-aloud-problem" role="alert">
          {problem}
        </span>
      ) : (
        <button type="button" className="link-button read-aloud-place" onClick={onShowVerse} title="Show the verse being read">
          {status === 'paused' ? 'Paused at ' : 'Reading '}
          {place?.reference ?? '…'}
        </button>
      )}
      {status !== 'idle' && (
        <>
          {status === 'paused' ? (
            <button type="button" className="primary-button small-button" onClick={onResume}>
              Resume
            </button>
          ) : (
            <button type="button" className="primary-button small-button" onClick={onPause}>
              Pause
            </button>
          )}
          <button type="button" className="secondary-button small-button" onClick={onStop}>
            Stop
          </button>
        </>
      )}
      {voices.length > 1 && (
        <label className="read-aloud-choice">
          Voice
          <select value={voiceName} onChange={(event) => onVoice(event.target.value)}>
            <option value="">The browser’s own</option>
            {voices.map((voice) => (
              <option key={voice.name} value={voice.name}>
                {voice.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <label className="read-aloud-choice">
        Speed
        <select value={rate} onChange={(event) => onRate(Number(event.target.value))}>
          {RATES.map((value) => (
            <option key={value} value={value}>
              {value === 1 ? 'Normal' : `${value}×`}
            </option>
          ))}
        </select>
      </label>
      {problem && (
        <button type="button" className="secondary-button small-button" onClick={onStop}>
          Close
        </button>
      )}
    </div>
  )
}

export default ReadAloudBar
