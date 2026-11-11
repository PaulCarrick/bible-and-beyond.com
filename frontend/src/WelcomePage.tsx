import type { ReactNode } from 'react'
import type { MusicSong } from './api'
import type { CommentarySource, DevotionalInfo, Translation } from './types'
import type { View } from './views'

// "A, B and C"
function joinList(items: string[]) {
  return items.length < 2 ? items.join('') : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}

const numberWords = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten']

// "two books", "one book", "12 books"
function countOf(count: number, singular: string, plural: string) {
  return `${numberWords[count] ?? count} ${count === 1 ? singular : plural}`
}

// Book titles in italics, joined like joinList ("A, B and C"), so titles that contain "and" stay apart.
function titleList(titles: string[]): ReactNode[] {
  return titles.flatMap((title, index) => [
    index === 0 ? '' : index === titles.length - 1 ? ' and ' : ', ',
    <em key={title}>{title}</em>,
  ])
}

// What the devotionals card says, built from the devotionals that are loaded (their names and whether each
// is read by the day or by the chapter), so it stays true when one is added or removed.
function describeDevotionals(devotionals: DevotionalInfo[]): ReactNode {
  const daily = devotionals.filter((entry) => entry.kind === 'daily').map((entry) => entry.name)
  const chapters = devotionals.filter((entry) => entry.kind === 'chapters').map((entry) => entry.name)
  return (
    <>
      {daily.length > 0 && <>Daily readings for every day of the year, opening at today&rsquo;s date, from {titleList(daily)}</>}
      {daily.length > 0 && chapters.length > 0 && '; and '}
      {chapters.length > 0 && (
        <>
          {daily.length > 0
            ? countOf(chapters.length, 'book', 'books')
            : countOf(chapters.length, 'book', 'books').replace(/^./, (first) => first.toUpperCase())}{' '}
          to read a chapter at a time: {titleList(chapters)}
        </>
      )}
      .
    </>
  )
}

interface WelcomePageProps {
  siteTitle: string
  translations: Translation[]
  commentaries: CommentarySource[]
  devotionals: DevotionalInfo[]
  otherBooks?: DevotionalInfo[]
  // The published songs of the Christian music section.
  songs?: MusicSong[]
  onNavigate: (view: View) => void
}

// The page the site opens on: what it is and what is in it. How to use it, and where the texts come from, are on
// the Help page.
function WelcomePage({ siteTitle, translations, commentaries, devotionals, otherBooks = [], songs = [], onNavigate }: WelcomePageProps) {
  const bibles = translations.filter((translation) => translation.source === 'local').map((translation) => translation.code)
  const licensed = translations
    .filter((translation) => translation.source === 'api_bible')
    .map((translation) => (translation.code === 'MSG' ? 'The Message' : translation.code))

  return (
    <div className="welcome">
      <h1>Welcome to {siteTitle}</h1>
      <p className="welcome-lead">
        {siteTitle} is a free, non-commercial site for reading and studying the Bible. It brings together
        public-domain Bibles, the Hebrew and Greek behind the English, cross references, classic commentaries and
        devotional books, so that from a single verse you can see what it says in the original languages, what other
        verses it points to, and what great teachers have written about it.
      </p>

      <h2>What you can do</h2>
      <div className="welcome-cards">
        <section className="welcome-card">
          <h3>The Bible</h3>
          <p>
            Read a chapter at a time in {bibles.length > 0 ? joinList(bibles) : 'the Bibles on this site'}, scrolling on
            from chapter to chapter and book to book, or search for words, phrases or a Strong&rsquo;s number such as{' '}
            <code>G0025</code> to find every verse that uses one Hebrew or Greek word.
            {licensed.length > 0 ? ` The ${joinList(licensed)} can be searched too.` : ''}
          </p>
          <div className="welcome-buttons">
            <button type="button" className="primary-button" onClick={() => onNavigate('read')}>
              Read the Bible
            </button>
            <button type="button" className="primary-button" onClick={() => onNavigate('bible')}>
              Search the Bible
            </button>
          </div>
        </section>
        {commentaries.length > 0 && (
          <section className="welcome-card">
            <h3>Commentaries</h3>
            <p>
              Choose a commentary and a verse and read on from there, chapter after chapter, or search the text of{' '}
              {joinList(commentaries.map((entry) => entry.short_name))}.
            </p>
            {/* Read first, then Search, as on the Bible card. */}
            <div className="welcome-buttons">
              <button type="button" className="primary-button" onClick={() => onNavigate('browse')}>
                Read the commentaries
              </button>
              <button type="button" className="primary-button" onClick={() => onNavigate('commentary')}>
                Search the commentaries
              </button>
            </div>
          </section>
        )}
        {devotionals.length > 0 && (
          <section className="welcome-card">
            <h3>Devotionals</h3>
            <p>
              {describeDevotionals(devotionals)} With an account, any of them can be emailed to you each day at a time
              you choose.
            </p>
            <div className="welcome-buttons">
              <button type="button" className="primary-button" onClick={() => onNavigate('devotionals')}>
                Read the devotionals
              </button>
            </div>
          </section>
        )}
        {otherBooks.length > 0 && (
          <section className="welcome-card">
            <h3>Other books</h3>
            <p>
              {otherBooks.length === 1 ? 'A book' : `${otherBooks.length} books`} to read a chapter at a time:{' '}
              {titleList(otherBooks.map((entry) => entry.name))}.
            </p>
            <div className="welcome-buttons">
              <button type="button" className="primary-button" onClick={() => onNavigate('books')}>
                Read other books
              </button>
              <button type="button" className="primary-button" onClick={() => onNavigate('searchBooks')}>
                Search other books
              </button>
            </div>
          </section>
        )}
        {songs.length > 0 && (
          <section className="welcome-card">
            <h3>Christian music</h3>
            {/* Only the count: the list of titles grew too long for the card. */}
            <p>
              {songs.length === 1 ? 'A song' : `${songs.length} songs`} to listen to, with their words.
            </p>
            <div className="welcome-buttons">
              <button type="button" className="primary-button" onClick={() => onNavigate('music')}>
                Listen to the music
              </button>
              <button type="button" className="primary-button" onClick={() => onNavigate('searchMusic')}>
                Search the music
              </button>
            </div>
          </section>
        )}
      </div>

      <p className="welcome-faq">
        Have a question about God, Jesus or the Bible? Try the{' '}
        <button type="button" className="link-button" onClick={() => onNavigate('faq')}>
          FAQ
        </button>{' '}
        page, where an AI answers common questions from the Bible.
      </p>
    </div>
  )
}

export default WelcomePage
