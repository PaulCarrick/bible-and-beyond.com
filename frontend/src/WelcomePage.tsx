import type { CommentarySource, DevotionalInfo, Translation } from './types'
import type { View } from './views'

// "A, B and C"
function joinList(items: string[]) {
  return items.length < 2 ? items.join('') : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}

interface WelcomePageProps {
  siteTitle: string
  translations: Translation[]
  commentaries: CommentarySource[]
  devotionals: DevotionalInfo[]
  onNavigate: (view: View) => void
}

// The page the site opens on: what it is, what is in it and how to use it.
function WelcomePage({ siteTitle, translations, commentaries, devotionals, onNavigate }: WelcomePageProps) {
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
          <h3>Read the Bible</h3>
          <p>
            Read a chapter at a time in {bibles.length > 0 ? joinList(bibles) : 'the Bibles on this site'}, scrolling on
            from chapter to chapter and book to book. Choose a Bible, book, chapter and verse to go straight there.
          </p>
          <button type="button" className="primary-button" onClick={() => onNavigate('read')}>
            Read the Bible
          </button>
        </section>
        <section className="welcome-card">
          <h3>Search the Bible</h3>
          <p>
            Search for words or phrases (all the words, any word, or an exact phrase), limit the search to some books, or
            type a Strong&rsquo;s number such as <code>G0025</code> to find every verse that uses one Hebrew or Greek
            word.
            {licensed.length > 0 ? ` The ${joinList(licensed)} can be searched too.` : ''}
          </p>
          <button type="button" className="primary-button" onClick={() => onNavigate('bible')}>
            Search the Bible
          </button>
        </section>
        {commentaries.length > 0 && (
          <section className="welcome-card">
            <h3>Commentaries</h3>
            <p>
              Search the text of {joinList(commentaries.map((entry) => entry.short_name))}, or choose a commentary and a
              verse and read on from there, chapter after chapter.
            </p>
            <div className="welcome-buttons">
              <button type="button" className="primary-button" onClick={() => onNavigate('commentary')}>
                Search the commentaries
              </button>
              <button type="button" className="primary-button" onClick={() => onNavigate('browse')}>
                Browse the commentaries
              </button>
            </div>
          </section>
        )}
        {devotionals.length > 0 && (
          <section className="welcome-card">
            <h3>Devotionals</h3>
            <p>
              Daily readings for every day of the year, opening at today&rsquo;s date, and two short classics of the
              devotional life: {joinList(devotionals.map((entry) => entry.name))}.
            </p>
            <button type="button" className="primary-button" onClick={() => onNavigate('devotionals')}>
              Open the devotionals
            </button>
          </section>
        )}
      </div>

      <h2>How to use it</h2>
      <ul className="welcome-tips">
        <li>
          <strong>Right-click a verse</strong> while reading (or click its number) for a menu: Show in Context, Full
          Chapter, Other Translations, Related Verses (cross references), Original Words (the Hebrew or Greek) and
          Commentaries. Search results have the same links under each verse.
        </li>
        <li>
          <strong>Click a word of the BSB</strong> to see the Hebrew or Greek word behind it, with its meaning and every
          verse that uses it.
        </li>
        <li>
          <strong>Follow the references.</strong> A Scripture reference inside a commentary or a devotional is a link to
          the verse. Back returns to where you were, and Escape closes the window.
        </li>
        <li>
          <strong>Keep scrolling.</strong> The readers load the next and the previous chapter as you go. The Home key,
          or the Back to top button, takes you to the top of the page.
        </li>
        <li>
          <strong>Search tips.</strong> Put a phrase in quotation marks to keep its words together. In the commentaries,
          words match in any form, so &ldquo;love&rdquo; also finds &ldquo;loved&rdquo;.
        </li>
      </ul>

      <h2>Contact</h2>
      <p>
        Questions, corrections or comments? Use the{' '}
        <button type="button" className="link-button" onClick={() => onNavigate('contact')}>
          contact form
        </button>
        .
      </p>

      <h2>About the texts</h2>
      <p>
        The Bibles you can read here, the commentaries and the devotionals are in the public domain.
        {licensed.length > 0
          ? ` The ${joinList(licensed)} are licensed to us through API.Bible; they can be searched but not read a chapter at a time.`
          : ''}{' '}
        The Hebrew and Greek data comes from STEP Bible and the cross references from OpenBible.info, both under a
        Creative Commons licence.{' '}
        <button type="button" className="link-button" onClick={() => onNavigate('copyright')}>
          Bible copyright notices
        </button>
      </p>
    </div>
  )
}

export default WelcomePage
