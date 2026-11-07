import StepBibleCredit from './StepBibleCredit'
import { verseButtonProps } from './verseAddress'
import type { ContextKind, LexiconEntry, VerseTarget } from './types'

interface LexiconPanelProps {
  entry: LexiconEntry
  translation: string
  onOpenVerse: (kind: ContextKind, target: VerseTarget) => void
}

function LexiconPanel({ entry, translation, onOpenVerse }: LexiconPanelProps) {
  const isHebrew = entry.language === 'hebrew'

  return (
    <>
      <div className="lexicon-head">
        <span className="lexicon-original" lang={isHebrew ? 'he' : 'el'} dir={isHebrew ? 'rtl' : 'ltr'}>
          {entry.original}
        </span>
        <span className="word-sound">{entry.transliteration}</span>
        <span className="lexicon-gloss">{entry.gloss}</span>
      </div>
      <p className="lexicon-definition">{entry.definition}</p>

      <h3 className="lexicon-usage">
        Used in {entry.verse_total.toLocaleString()} {entry.verse_total === 1 ? 'verse' : 'verses'}
      </h3>
      <ol className="related-list">
        {entry.verses.map((verse) => (
          <li key={`${verse.book_number}-${verse.chapter}-${verse.verse}`} className="related-item">
            <strong className="related-reference">{verse.reference}</strong>
            {verse.text === null ? (
              <p className="related-missing">This verse is not in {translation}.</p>
            ) : (
              <p className="related-text">{verse.text}</p>
            )}
            <div className="related-actions">
              <button
                type="button"
                className="link-button"
                {...verseButtonProps(
                  { translation, book: verse.book_number, chapter: verse.chapter, verse: verse.verse },
                  () =>
                    onOpenVerse('context', {
                      translation,
                      book_number: verse.book_number,
                      chapter: verse.chapter,
                      verse: verse.verse,
                      reference: verse.reference,
                    }),
                )}
              >
                Show in Context
                <span className="visually-hidden"> for {verse.reference}</span>
              </button>
              <button
                type="button"
                className="link-button"
                onClick={() =>
                  onOpenVerse('words', {
                    translation,
                    book_number: verse.book_number,
                    chapter: verse.chapter,
                    verse: verse.verse,
                    reference: verse.reference,
                  })
                }
              >
                Original Words
                <span className="visually-hidden"> of {verse.reference}</span>
              </button>
            </div>
          </li>
        ))}
      </ol>
      <p className="related-note">
        {entry.verse_total > entry.shown
          ? `Showing the first ${entry.shown} of ${entry.verse_total.toLocaleString()} verses, in Bible order. `
          : ''}
        <StepBibleCredit />
      </p>
    </>
  )
}

export default LexiconPanel
