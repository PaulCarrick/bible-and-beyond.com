import StepBibleCredit from './StepBibleCredit'
import type { ContextKind, OriginalWordsResponse, VerseTarget } from './types'

interface WordsPanelProps {
  words: OriginalWordsResponse
  translation: string
  onOpenVerse: (kind: ContextKind, target: VerseTarget) => void
}

function WordsPanel({ words, translation, onOpenVerse }: WordsPanelProps) {
  const isHebrew = words.language === 'hebrew'
  const reference = `${words.book_name} ${words.chapter}:${words.verse}`

  return (
    <>
      <p className="words-intro">
        {isHebrew ? 'Hebrew' : 'Greek'} words of {reference}, in reading order. Choose a Strong&rsquo;s number to
        see what the word means and where else it is used.
      </p>
      <ol className="words-list">
        {words.words.map((word, index) => (
          <li key={index} className="word-item">
            <span className="word-original" lang={isHebrew ? 'he' : 'el'} dir={isHebrew ? 'rtl' : 'ltr'}>
              {word.original}
            </span>
            <span className="word-sound">{word.transliteration}</span>
            <span className="word-english">{word.english}</span>
            <span className="word-gloss">{word.gloss}</span>
            {word.strong_code && (
              <button
                type="button"
                className="link-button word-strong"
                onClick={() =>
                  onOpenVerse('lexicon', {
                    translation,
                    book_number: words.book_number,
                    chapter: words.chapter,
                    verse: words.verse,
                    reference: word.strong_code ?? '',
                    strong_code: word.strong_code ?? '',
                  })
                }
              >
                {word.strong_code}
                <span className="visually-hidden"> lexicon entry for {word.transliteration}</span>
              </button>
            )}
          </li>
        ))}
      </ol>
      <p className="related-note">
        <StepBibleCredit />
      </p>
    </>
  )
}

export default WordsPanel
