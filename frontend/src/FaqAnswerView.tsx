import type { ReactNode } from 'react'
import type { FaqReference } from './api'
import MarkdownText from './MarkdownText'
import type { TextLink } from './MarkdownText'
import { verseAddress } from './verseAddress'

interface FaqAnswerViewProps {
  question: string
  // Markdown written by Gemini; drawn as text, never as HTML.
  answer: string
  references: FaqReference[]
  // Shown between the answer and the AI note (the site owner's note on one question).
  children?: ReactNode
}

// An AI answer on the FAQ page (to a listed question or the visitor's own): the question, the answer with
// its Scripture references as links that open the Bible in a new tab, and the note that an AI wrote it.
function FaqAnswerView({ question, answer, references, children }: FaqAnswerViewProps) {
  return (
    <article className="faq-answer">
      <h2>{question}</h2>
      <MarkdownText
        markdown={answer}
        links={references.map(
          (reference): TextLink => ({
            text: reference.text,
            label: `${reference.text} (opens the Bible in a new tab)`,
            href: verseAddress('BSB', reference.book, reference.chapter, reference.verse),
          }),
        )}
      />
      {children}
      <div className="faq-ai-note">
        <p>
          This answer was written by an AI and may contain mistakes. This is true of people as well: for example, the
          Gnostic heresy of the 1st and 2nd centuries. John warns us in{' '}
          <a href={verseAddress('BSB', 62, 4, 1)} target="_blank" rel="noopener" aria-label="1 John 4:1 (opens the Bible in a new tab)">
            1 John 4:1
          </a>
          :
        </p>
        <blockquote className="faq-ai-verse">
          &ldquo;Beloved, do not believe every spirit, but test the spirits to see whether they are from God. For many
          false prophets have gone out into the world.&rdquo; (BSB)
        </blockquote>
        <p>
          Check what it says against the Bible itself (you can do this on this site), and talk over important questions
          with a pastor or a trusted Christian friend.
        </p>
      </div>
    </article>
  )
}

export default FaqAnswerView
