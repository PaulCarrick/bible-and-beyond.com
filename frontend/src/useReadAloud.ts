import { useCallback, useEffect, useRef, useState } from 'react'
import type { BibleChapter } from './types'

// Read aloud (added 2026-11-26 at the owner's request), in the Bible reader: the browser's own voice
// (the Web Speech API, so nothing is sent anywhere and nothing costs), one verse at a time so the verse being read can
// be highlighted, then on into the next chapter by itself, with "Book chapter N" read before each chapter. The voice
// and speed the reader chose are remembered in this browser.

export interface ReadingPlace {
  book: number
  chapter: number
  verse: number
  // "John 3:16", for the player.
  reference: string
}

export type ReadAloudStatus = 'idle' | 'playing' | 'paused'

const VOICE_KEY = 'read-aloud-voice'
const RATE_KEY = 'read-aloud-rate'

function remembered(key: string): string {
  try {
    return window.localStorage.getItem(key) ?? ''
  } catch {
    return ''
  }
}

function remember(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // Storage may be blocked: the choice then lasts only this visit.
  }
}

export function canReadAloud(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window && typeof SpeechSynthesisUtterance !== 'undefined'
}

// loadChapter: a chapter of the same Bible (the reader's own copy when it has it loaded).
// onVerse: the verse now being read, to highlight it and keep it in view.
export function useReadAloud(
  loadChapter: (book: number, chapter: number) => Promise<BibleChapter>,
  onVerse: (place: ReadingPlace | null) => void,
) {
  const [status, setStatus] = useState<ReadAloudStatus>('idle')
  const [place, setPlace] = useState<ReadingPlace | null>(null)
  const [problem, setProblem] = useState('')
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([])
  const [voiceName, setVoiceNameState] = useState(() => remembered(VOICE_KEY))
  const [rate, setRateState] = useState(() => Number(remembered(RATE_KEY)) || 1)
  // Each reading has its own number, so the end of an utterance from a reading that was stopped is ignored.
  const run = useRef(0)
  // The lines queued to be spoken. Chrome drops the events of an utterance nothing holds on to (so the next verse
  // never started; found 2026-11-26), so they are kept here until the reading ends.
  const queued = useRef<SpeechSynthesisUtterance[]>([])
  const settings = useRef({ voiceName, rate, voices })
  const callbacks = useRef({ loadChapter, onVerse })
  useEffect(() => {
    settings.current = { voiceName, rate, voices }
    callbacks.current = { loadChapter, onVerse }
  })

  // The voices arrive a moment after the page loads in some browsers.
  useEffect(() => {
    if (!canReadAloud()) {
      return
    }
    const update = () => setVoices(window.speechSynthesis.getVoices())
    update()
    window.speechSynthesis.addEventListener('voiceschanged', update)
    return () => window.speechSynthesis.removeEventListener('voiceschanged', update)
  }, [])

  // Ends the reading (a problem, if any, stays shown).
  const halt = useCallback(() => {
    run.current += 1
    if (canReadAloud()) {
      window.speechSynthesis.cancel()
    }
    queued.current = []
    setStatus('idle')
    setPlace(null)
    callbacks.current.onVerse(null)
  }, [])

  const stop = useCallback(() => {
    halt()
    setProblem('')
  }, [halt])

  // Stops reading when the page goes away.
  useEffect(() => () => {
    run.current += 1
    if (canReadAloud()) {
      window.speechSynthesis.cancel()
    }
  }, [])

  function say(spoken: SpeechSynthesisUtterance) {
    // Only the last few are needed: the ones spoken and queued.
    queued.current = [...queued.current.slice(-4), spoken]
    window.speechSynthesis.speak(spoken)
  }

  function utterance(text: string, language: string): SpeechSynthesisUtterance {
    const spoken = new SpeechSynthesisUtterance(text)
    const { voiceName: name, rate: speed, voices: list } = settings.current
    const voice = list.find((entry) => entry.name === name)
    if (voice) {
      spoken.voice = voice
      spoken.lang = voice.lang
    } else {
      spoken.lang = language
    }
    spoken.rate = speed
    return spoken
  }

  // Reads the verse at index in chapter, then the ones after it, then the next chapters.
  function readFrom(chapter: BibleChapter, index: number, thisRun: number) {
    if (thisRun !== run.current) {
      return
    }
    const verse = chapter.verses[index]
    if (!verse) {
      void readNextChapter(chapter, thisRun)
      return
    }
    const language = chapter.translation.language || 'en'
    if (index === 0) {
      // The chapter's name first, as a narrator would.
      say(utterance(`${chapter.book_name}, chapter ${chapter.chapter}.`, language))
    }
    const spoken = utterance(verse.text, language)
    const here: ReadingPlace = {
      book: chapter.book_number,
      chapter: chapter.chapter,
      verse: verse.verse,
      reference: `${chapter.book_name} ${chapter.chapter}:${verse.verse}`,
    }
    spoken.onstart = () => {
      if (thisRun === run.current) {
        setPlace(here)
        callbacks.current.onVerse(here)
      }
    }
    spoken.onend = () => readFrom(chapter, index + 1, thisRun)
    spoken.onerror = (event) => {
      // A reading stopped or replaced ends its utterances this way.
      if (event.error === 'interrupted' || event.error === 'canceled' || thisRun !== run.current) {
        return
      }
      setProblem('The browser could not read this aloud.')
      halt()
    }
    say(spoken)
  }

  async function readNextChapter(chapter: BibleChapter, thisRun: number) {
    if (!chapter.next) {
      // The end of the Bible.
      halt()
      return
    }
    try {
      const next = await callbacks.current.loadChapter(chapter.next.book_number, chapter.next.chapter)
      readFrom(next, 0, thisRun)
    } catch {
      if (thisRun === run.current) {
        setProblem('The next chapter could not be loaded.')
        halt()
      }
    }
  }

  function start(chapter: BibleChapter, verseNumber: number) {
    if (!canReadAloud()) {
      return
    }
    run.current += 1
    window.speechSynthesis.cancel()
    setProblem('')
    setStatus('playing')
    const index = Math.max(0, chapter.verses.findIndex((entry) => entry.verse === verseNumber))
    readFrom(chapter, index, run.current)
  }

  function pause() {
    window.speechSynthesis.pause()
    setStatus('paused')
  }

  function resume() {
    window.speechSynthesis.resume()
    setStatus('playing')
  }

  function setVoiceName(name: string) {
    setVoiceNameState(name)
    remember(VOICE_KEY, name)
  }

  function setRate(value: number) {
    setRateState(value)
    remember(RATE_KEY, String(value))
  }

  return { status, place, problem, voices, voiceName, setVoiceName, rate, setRate, start, pause, resume, stop }
}
