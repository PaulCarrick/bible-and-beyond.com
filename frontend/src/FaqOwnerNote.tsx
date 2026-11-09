import type { ReactNode } from 'react'
import { verseAddress } from './verseAddress'

// The questions that have a note from the site owner. They are matched by their words, not their numbers,
// because the numbers move when a question is added, so rewording a question drops its note.
const LGBTQ_QUESTION = 'How should Christians understand LGBTQ identities and relationships?'
const REPEATED_SIN_QUESTION = 'How can I overcome a sin I keep repeating?'

// The question the note points to ("see the FAQ on grace").
const GRACE_QUESTION = 'Is a Christian saved by grace alone?'

interface FaqOwnerNoteProps {
  // The question whose answer is shown; the note appears only for a question that has one.
  question: string
  // Shows another FAQ question's answer on this page.
  onShowQuestion: (question: string) => void
}

const CELEBRATE_RECOVERY_ADDRESS = 'https://celebraterecovery.com/'

// A link to Celebrate Recovery's website, in a new tab.
function CelebrateRecoveryLink() {
  return (
    <a href={CELEBRATE_RECOVERY_ADDRESS} target="_blank" rel="noopener" aria-label="Celebrate Recovery (opens its website in a new tab)">
      Celebrate Recovery
    </a>
  )
}

// The box the notes are drawn in, set apart from the AI's answer.
function OwnerNoteBox({ children }: { children: ReactNode }) {
  return (
    <aside className="faq-owner-note" aria-labelledby="faq-owner-note-heading">
      <h2 id="faq-owner-note-heading">A note from the site owner</h2>
      {children}
    </aside>
  )
}

interface VerseLinkProps {
  book: number
  chapter: number
  verse: number
  // The Strong's number of a Hebrew or Greek word, to open its lexicon entry over the verse.
  strongCode?: string
  label: string
  children: ReactNode
}

// A link that opens the Bible reader (BSB) in a new tab, so the FAQ stays open, like the links in the answers.
function VerseLink({ book, chapter, verse, strongCode, label, children }: VerseLinkProps) {
  return (
    <a href={verseAddress('BSB', book, chapter, verse, strongCode)} target="_blank" rel="noopener" aria-label={`${label} (opens in a new tab)`}>
      {children}
    </a>
  )
}

interface PassageProps {
  book: number
  chapter: number
  verse: number
  reference: string
  children: ReactNode
}

// A quotation from the Bible (BSB, public domain) with a link to it underneath.
function Passage({ book, chapter, verse, reference, children }: PassageProps) {
  return (
    <blockquote className="faq-owner-passage">
      <p>{children}</p>
      <footer>
        —{' '}
        <VerseLink book={book} chapter={chapter} verse={verse} label={reference}>
          {reference}
        </VerseLink>
      </footer>
    </blockquote>
  )
}

// The note under the AI's answer to the LGBTQ question.
function LgbtqNote({ onShowQuestion }: { onShowQuestion: (question: string) => void }) {
  return (
    <OwnerNoteBox>
      <p>
        This is a very controversial subject, and I’m sure I am going to make many people angry. In my opinion, too
        much emphasis has been placed on sexual sin.
      </p>
      <Passage book={45} chapter={3} verse={23} reference="Romans 3:23–24">
        “For all have sinned and fall short of the glory of God, and are justified freely by His grace through the
        redemption that is in Christ Jesus.”
      </Passage>
      <Passage book={42} chapter={6} verse={37} reference="Luke 6:37">
        “Do not judge, and you will not be judged. Do not condemn, and you will not be condemned. Forgive, and you will
        be forgiven.”
      </Passage>
      <p>
        We are told not to judge. The Greek word for sin is{' '}
        <VerseLink book={45} chapter={3} verse={23} strongCode="G0264" label="ἁμαρτάνω, hamartanō, in the Greek lexicon">
          <strong lang="grc">ἁμαρτάνω</strong> (<em>hamartanō</em>)
        </VerseLink>
        : “to sin, to miss the mark; hence, to err, to do wrong.” The term comes from archery and means that you
        missed the target. It doesn’t matter whether you miss by inches or by yards. We all sin daily.
      </p>
      <p>Jesus set a high bar for sin:</p>
      <Passage book={40} chapter={19} verse={9} reference="Matthew 19:9">
        “Now I tell you that whoever divorces his wife, except for sexual immorality, and marries another woman commits
        adultery.”
      </Passage>
      <p>
        Most Protestants no longer have a problem with divorce. I have many good Christian friends who have been
        divorced and remarried.
      </p>
      <p>Here is another:</p>
      <Passage book={40} chapter={5} verse={22} reference="Matthew 5:22">
        “But I tell you that anyone who is angry with his brother will be subject to judgment. Again, anyone who says
        to his brother, ‘Raca,’ will be subject to the Sanhedrin. But anyone who says, ‘You fool!’ will be subject to
        the fire of hell.”
      </Passage>
      <p>
        So it is evident that we all sin. How, then, can anyone be saved? By grace (see the{' '}
        <a
          href="/faq"
          onClick={(event) => {
            event.preventDefault()
            onShowQuestion(GRACE_QUESTION)
          }}
        >
          FAQ on grace
        </a>
        ). Grace overcomes the law. I don’t know about you, but I love pork, lobster and crab, all of which are
        forbidden in the Old Testament. As Paul says:
      </p>
      <Passage book={45} chapter={8} verse={1} reference="Romans 8:1–4">
        “Therefore, there is now no condemnation for those who are in Christ Jesus. For in Christ Jesus the law of the
        Spirit of life set you free from the law of sin and death. For what the law was powerless to do in that it was
        weakened by the flesh, God did by sending His own Son in the likeness of sinful man, as an offering for sin. He
        thus condemned sin in the flesh, so that the righteous standard of the law might be fulfilled in us, who do not
        walk according to the flesh but according to the Spirit.”
      </Passage>
      <p>I also have a few gay and lesbian Christian friends. As Paul said:</p>
      <Passage book={54} chapter={1} verse={16} reference="1 Timothy 1:16">
        “But for this very reason I was shown mercy, so that in me, the worst of sinners, Christ Jesus might display
        His perfect patience as an example to those who would believe in Him for eternal life.”
      </Passage>
      <p>I feel the same way as the Apostle Paul (and those of you who know me know this).</p>
      <p>
        I love the motto of my church: <em>“In essential things, unity; in non-essential things, liberty; in all
        things, grace.”</em> So for me, if my brother or sister is divorced, gay or lesbian, addicted to alcohol or
        gambling, or struggling with anything else, it doesn’t matter. They are my brother or sister, saved by grace,
        and I love them.
      </p>
      <p>
        If anyone is struggling with a hurt, habit or hang-up, I highly recommend{' '}
        <CelebrateRecoveryLink />. It is a Christian-based recovery program. It is not limited to addiction; it covers many other issues:
        depression, grief, divorce, codependency, sexual addiction, anger issues and many more.
      </p>
      <Passage book={40} chapter={22} verse={36} reference="Matthew 22:36–40">
        “Teacher, which commandment is the greatest in the Law?” Jesus declared, “‘Love the Lord your God with all your
        heart and with all your soul and with all your mind.’ This is the first and greatest commandment. And the
        second is like it: ‘Love your neighbor as yourself.’ All the Law and the Prophets hang on these two
        commandments.”
      </Passage>
      <p>
        Grace trumps the law. If you are following the two greatest commandments, any specific sin is irrelevant.
      </p>
    </OwnerNoteBox>
  )
}

// The note under the AI's answer to the question about a sin that keeps coming back.
function RepeatedSinNote() {
  return (
    <OwnerNoteBox>
      <p>
        If you need help, <CelebrateRecoveryLink /> may be a place to reach out to. They are there for help with your
        hurts, habits, or hangups. It’s not only about addictions. It can help with grief, mental health issues
        (depression, etc.), divorce, codependence, sexual or gambling issues and many more.
      </p>
      <p>
        Many churches have Celebrate Recovery as one of their ministries and even if your church doesn’t, there may be
        a church near you that has meetings.
      </p>
      <p>Personally, I help with CR at our church and I find it very useful for my hurts, habits and hangups.</p>
    </OwnerNoteBox>
  )
}

// The site owner's own note for the question shown, in a box between the AI's answer and its AI note, or
// nothing when that question has none.
function FaqOwnerNote({ question, onShowQuestion }: FaqOwnerNoteProps) {
  if (question === LGBTQ_QUESTION) {
    return <LgbtqNote onShowQuestion={onShowQuestion} />
  }
  if (question === REPEATED_SIN_QUESTION) {
    return <RepeatedSinNote />
  }
  return null
}

export default FaqOwnerNote
